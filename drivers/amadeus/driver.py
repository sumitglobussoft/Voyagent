"""The Amadeus driver — satisfies :class:`FareSearchDriver` + :class:`PNRDriver`.

This driver targets **Amadeus Self-Service** (the developer-portal sandbox
at ``https://test.api.amadeus.com``). Self-Service is booking-only; ticket
issuance and voiding do not exist here. Those capabilities are declared
``not_supported`` in :meth:`manifest` and raise
:class:`CapabilityNotSupportedError` at runtime — this is honest. A future
``drivers/amadeus_enterprise`` will declare them ``full``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from drivers._contracts.cache import OfferCache
from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    PermanentError,
)
from drivers._contracts.fare_search import FareSearchCriteria
from drivers._contracts.manifest import CapabilityManifest
from schemas.canonical import EntityId, Fare, PNR, PNRStatus, Ticket

from .client import AmadeusClient
from .config import AmadeusConfig
from .errors import DRIVER_NAME
from .mapping import (
    _new_entity_id,
    amadeus_offer_to_fares,
    amadeus_order_to_pnr,
    criteria_to_query_params,
)

# Amadeus offers typically expire in 15–30 minutes. Twenty minutes is a
# conservative default — enough headroom for the agent to gather traveler
# details and gain human approval, short enough that we don't keep stale
# prices around. The runtime may override per call.
_OFFER_TTL_SECONDS = 20 * 60
# Below this remaining TTL (minutes), we re-price the offer before booking.
_REPRICE_THRESHOLD_SECONDS = 5 * 60

logger = logging.getLogger(__name__)


class AmadeusDriver:
    """Reference driver implementing fare search and partial PNR lifecycle.

    Construct once per tenant with an :class:`AmadeusConfig`. Methods are
    ``async`` and safe for concurrent use. The driver intentionally exposes
    the bare capability Protocol signatures — callers that need vendor-only
    context (e.g. the raw Amadeus offer JSON for ``create``) supply it via
    the runtime's offer cache, not via signature changes.
    """

    name: ClassVar[str] = "amadeus"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        config: AmadeusConfig,
        *,
        client: AmadeusClient | None = None,
        tenant_id: EntityId | None = None,
        offer_cache: OfferCache | None = None,
    ) -> None:
        self._config = config
        self._client = client or AmadeusClient(config)
        # tenant_id is required to materialize canonical records; we let
        # callers supply a synthetic id when not in a multi-tenant context
        # (e.g. tests, scripts).
        self._tenant_id: EntityId = tenant_id or _new_entity_id()
        # When present, ``search`` populates the cache with each offer's
        # raw vendor JSON so ``create`` can re-post it. The runtime
        # constructs a shared cache via :func:`build_offer_cache` and
        # injects it here — tests supply an ``InMemoryOfferCache``.
        self._offer_cache: OfferCache | None = offer_cache

    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Driver protocol                                                    #
    # ------------------------------------------------------------------ #

    def manifest(self) -> CapabilityManifest:
        """Return the static capability manifest for this driver."""
        return CapabilityManifest(
            driver=self.name,
            version=self.version,
            implements=["FareSearchDriver", "PNRDriver"],
            capabilities={
                "search": "full",
                "create": "full",
                "read": "full",
                "cancel": "full",
                "queue_read": "not_supported",
                "issue_ticket": "not_supported",
                "void_ticket": "not_supported",
            },
            transport=["rest"],
            requires=["tenant_credentials"],
            tenant_config_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["client_id", "client_secret"],
                "properties": {
                    "api_base": {"type": "string", "format": "uri"},
                    "client_id": {"type": "string", "minLength": 1},
                    "client_secret": {"type": "string", "minLength": 1},
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
                    "max_retries": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        )

    # ------------------------------------------------------------------ #
    # FareSearchDriver                                                   #
    # ------------------------------------------------------------------ #

    async def search(self, criteria: FareSearchCriteria) -> list[Fare]:
        """Shop ``GET /v2/shopping/flight-offers`` and return canonical fares.

        When an :class:`OfferCache` is configured the raw vendor offer
        JSON is cached against every canonical ``Fare.id`` produced from
        that offer, keyed via :func:`_offer_cache_key`. ``create`` then
        re-reads the offer to build the booking payload.

        Raises: any of the standard driver errors — see
        :meth:`FareSearchDriver.search`.
        """
        params = criteria_to_query_params(criteria)
        params["max"] = "50"  # Amadeus caps at 250; 50 is plenty for v0.
        body = await self._client.get_json("/v2/shopping/flight-offers", params=params)

        offers = (body or {}).get("data") or []
        total_pax = sum(criteria.passengers.values())
        itinerary_id = _new_entity_id()
        # We don't have real passenger ids at this layer — generate synthetic
        # ones so Fare is well-formed. The agent runtime remaps fare.passenger_id
        # to real Passenger ids when it persists the quote.
        synthetic_pax_ids = [_new_entity_id() for _ in range(total_pax)]

        fares: list[Fare] = []
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            traveler_count = len(offer.get("travelerPricings") or [])
            pax_slice = synthetic_pax_ids[:traveler_count] if traveler_count else synthetic_pax_ids
            if len(pax_slice) != traveler_count:
                # Shape drift — skip rather than abort the whole search.
                logger.warning(
                    "amadeus: offer %s has %d travelerPricings, expected %d; skipping.",
                    offer.get("id"),
                    traveler_count,
                    total_pax,
                )
                continue
            offer_fares = amadeus_offer_to_fares(
                offer,
                passenger_ids=pax_slice,
                itinerary_id=itinerary_id,
                tenant_id=self._tenant_id,
            )
            # Cache the raw offer under every fare id it produced so
            # ``create`` can retrieve it by any single fare later.
            if self._offer_cache is not None:
                for fare in offer_fares:
                    try:
                        await self._offer_cache.put(
                            _offer_cache_key(fare.id),
                            offer,
                            ttl_seconds=_OFFER_TTL_SECONDS,
                        )
                    except Exception:  # noqa: BLE001 — cache is best-effort
                        logger.warning(
                            "amadeus: offer cache put failed for fare %s",
                            fare.id,
                            exc_info=True,
                        )
            fares.extend(offer_fares)

        if criteria.max_price is not None:
            fares = [
                f
                for f in fares
                if f.total.currency == criteria.max_price.currency
                and f.total.amount <= criteria.max_price.amount
            ]
        return fares

    # ------------------------------------------------------------------ #
    # PNRDriver                                                          #
    # ------------------------------------------------------------------ #

    async def create(
        self,
        fare_ids: list[EntityId],
        passenger_ids: list[EntityId],
    ) -> PNR:
        """Create a flight-order from cached offer(s).

        Amadeus Self-Service requires the agent to POST the original
        flight-offer JSON. This driver sources that JSON from an
        :class:`OfferCache` populated during :meth:`search`.

        The flow:
          1. Read one cached offer per ``fare_id``. Multiple
             ``fare_ids`` from the same offer collapse to a single
             cached entry (Amadeus books a whole offer at once).
          2. If the offer's ``lastTicketingDateTime`` is close to
             expiry, re-price via ``POST
             /v1/shopping/flight-offers/pricing`` and use the returned
             offer instead.
          3. Synthesise minimal ``travelers`` blocks (one per
             ``passenger_id``) — richer passenger detail will be
             wired when the runtime exposes Passenger lookups.
          4. POST ``/v1/booking/flight-orders`` and map the response
             through :func:`amadeus_order_to_pnr`.

        Raises :class:`PermanentError` on cache miss — the caller must
        re-run ``search`` and try again with fresh fare ids.
        """
        if self._offer_cache is None:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create requires an offer cache; none was "
                "configured on this driver instance.",
            )
        if not fare_ids:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create: fare_ids must not be empty.",
            )

        # Collect distinct offers — multiple fare_ids from the same
        # offer (one per passenger) point at one cached entry.
        seen_offer_ids: set[str] = set()
        offers_to_book: list[dict[str, Any]] = []
        for fid in fare_ids:
            cached = await self._offer_cache.get(_offer_cache_key(fid))
            if cached is None:
                raise PermanentError(
                    DRIVER_NAME,
                    f"offer_expired_or_not_cached: fare_id={fid!r}. Re-run "
                    "search before booking — Amadeus offers have a 15–30 "
                    "minute TTL and Voyagent caches them for 20 minutes.",
                )
            off_id = str(cached.get("id") or fid)
            if off_id in seen_offer_ids:
                continue
            seen_offer_ids.add(off_id)
            offers_to_book.append(cached)

        # Re-price if any offer is close to expiry. Amadeus's pricing
        # endpoint accepts the exact shape it returned from shopping.
        refreshed: list[dict[str, Any]] = []
        for offer in offers_to_book:
            if _needs_reprice(offer):
                repriced = await self._reprice(offer)
                refreshed.append(repriced)
            else:
                refreshed.append(offer)

        travelers_payload = _synthesize_travelers(passenger_ids)

        body = {
            "data": {
                "type": "flight-order",
                "flightOffers": refreshed,
                "travelers": travelers_payload,
            }
        }
        response = await self._client.post_json(
            "/v1/booking/flight-orders", json=body
        )
        order = (response or {}).get("data") if isinstance(response, dict) else None
        if not isinstance(order, dict):
            raise PermanentError(
                DRIVER_NAME,
                "Amadeus create: unexpected payload shape — missing 'data'.",
            )

        # Drop the cache entries we just consumed so a retry that
        # accidentally re-submits the same fare_ids returns a clean
        # error rather than double-booking.
        for fid in fare_ids:
            try:
                await self._offer_cache.delete(_offer_cache_key(fid))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "amadeus: cache delete failed for fare %s", fid, exc_info=True
                )

        return amadeus_order_to_pnr(order, tenant_id=self._tenant_id)

    async def _reprice(self, offer: dict[str, Any]) -> dict[str, Any]:
        """POST the offer to the pricing endpoint and return the fresh copy.

        Amadeus returns the same flight-offer shape back, typically
        with refreshed ``lastTicketingDateTime`` and possibly adjusted
        prices. We surface the new offer to the caller so downstream
        bookings post the authoritative version.
        """
        pricing_body = {
            "data": {
                "type": "flight-offers-pricing",
                "flightOffers": [offer],
            }
        }
        response = await self._client.post_json(
            "/v1/shopping/flight-offers/pricing", json=pricing_body
        )
        data = (response or {}).get("data") if isinstance(response, dict) else None
        offers = (
            (data or {}).get("flightOffers") if isinstance(data, dict) else None
        )
        if not isinstance(offers, list) or not offers:
            # Re-pricing failure is a permanent error for this booking —
            # better to abort than to POST a stale offer.
            raise PermanentError(
                DRIVER_NAME,
                "Amadeus reprice: response did not contain any flightOffers.",
            )
        return offers[0]

    async def read(self, locator: str) -> PNR:
        """Fetch an order by Amadeus **order id**.

        NOTE: Amadeus keys orders by their own ``id`` (e.g. ``eJzTd9f3NjIJ...``),
        not by the airline record locator. Callers that only have a 6-char
        record locator cannot use this endpoint — they must round-trip through
        the original ``create`` response where both ids are exposed.
        """
        body = await self._client.get_json(f"/v1/booking/flight-orders/{locator}")
        order = (body or {}).get("data") if isinstance(body, dict) else None
        if not isinstance(order, dict):
            raise PermanentError(
                DRIVER_NAME,
                f"Amadeus read: unexpected payload shape for order {locator!r}.",
            )
        return amadeus_order_to_pnr(order, tenant_id=self._tenant_id)

    async def cancel(self, pnr_id: EntityId) -> PNR:
        """Cancel the order. Amadeus returns 204 on success.

        We follow up with a GET so we can return the updated canonical PNR,
        matching the Protocol contract that requires a PNR instance back.
        """
        await self._client.delete(f"/v1/booking/flight-orders/{pnr_id}")
        try:
            return await self.read(pnr_id)
        except Exception:  # pragma: no cover - best-effort readback
            # If Amadeus has already purged the order post-cancel, synthesize
            # a canonical cancelled PNR so downstream state converges.
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            return PNR(
                id=_new_entity_id(),
                tenant_id=self._tenant_id,
                locator=pnr_id,
                source=self.name,
                source_ref=pnr_id,
                status=PNRStatus.CANCELLED,
                passenger_ids=[_new_entity_id()],
                segment_ids=[_new_entity_id()],
                fare_ids=[],
                created_at=now,
                updated_at=now,
            )

    async def queue_read(self, queue_number: int) -> list[PNR]:
        """Not supported by Amadeus Self-Service."""
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "Amadeus Self-Service does not expose GDS queues. Use an "
            "Amadeus-Enterprise driver for queue operations.",
        )

    async def issue_ticket(self, pnr_id: EntityId) -> list[Ticket]:
        """Not supported on the Self-Service API.

        Ticket issuance is available only on Amadeus Enterprise / Selling
        Platform. The future ``drivers.amadeus_enterprise`` driver will
        implement this and declare ``issue_ticket = full`` in its manifest.
        """
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "Amadeus Self-Service does not issue tickets. Use the "
            "Amadeus-Enterprise driver (forthcoming) or route to another "
            "ticketing driver (BSPDriver).",
        )

    async def void_ticket(self, ticket_id: EntityId) -> Ticket:
        """Not supported on the Self-Service API (see :meth:`issue_ticket`)."""
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "Amadeus Self-Service does not void tickets. Use the "
            "Amadeus-Enterprise driver (forthcoming).",
        )

    # ------------------------------------------------------------------ #
    # Context manager                                                    #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> AmadeusDriver:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# Offer-cache helpers                                                         #
# --------------------------------------------------------------------------- #


def _offer_cache_key(fare_id: EntityId) -> str:
    """Stable cache key for a canonical fare id.

    Prefixed so the shared Redis namespace stays tidy when other
    components start caching things alongside the driver.
    """
    return f"amadeus:fare:{fare_id}"


def _needs_reprice(offer: dict[str, Any]) -> bool:
    """True when the offer's ticketing deadline is under the threshold.

    Amadeus returns ``lastTicketingDateTime`` without a timezone
    offset; we treat it as UTC here — consistent with the rest of the
    driver's datetime handling (see :mod:`mapping`). When the field is
    absent we assume the offer is still fresh; pricing is cheap to run
    opportunistically if the booking fails.
    """
    from datetime import datetime, timezone

    raw = offer.get("lastTicketingDateTime")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    return remaining < _REPRICE_THRESHOLD_SECONDS


def _synthesize_travelers(passenger_ids: list[EntityId]) -> list[dict[str, Any]]:
    """Build minimal Amadeus ``travelers`` blocks from canonical ids.

    v0 does not round-trip through the canonical ``Passenger`` registry
    yet — the PNR contract passes ids only. We emit placeholder
    traveler objects so the booking payload has the required shape; a
    richer implementation will join to :class:`Passenger` and fill in
    names, dates of birth, contact info, and documents.

    TODO(voyagent-amadeus): integrate with a PassengerResolver once
    the runtime exposes one.
    """
    travelers: list[dict[str, Any]] = []
    for idx, pid in enumerate(passenger_ids, start=1):
        travelers.append(
            {
                "id": str(idx),
                "dateOfBirth": "1990-01-01",
                "name": {"firstName": "PLACEHOLDER", "lastName": "TRAVELER"},
                "gender": "UNSPECIFIED",
                "contact": {
                    "emailAddress": "placeholder@example.com",
                    "phones": [
                        {
                            "deviceType": "MOBILE",
                            "countryCallingCode": "1",
                            "number": "5550000000",
                        }
                    ],
                },
                # Embed the canonical id so the audit trail can join
                # back even though Amadeus ignores unknown fields.
                "meta": {"voyagent_passenger_id": str(pid)},
            }
        )
    return travelers


__all__ = ["AmadeusDriver"]
