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
    ValidationFailedError,
)
from drivers._contracts.fare_search import FareSearchCriteria
from drivers._contracts.manifest import CapabilityManifest
from drivers._contracts.passenger_resolver import PassengerResolver
from schemas.canonical import (
    EntityId,
    Fare,
    Gender,
    Passenger,
    Passport,
    PNR,
    PNRStatus,
    Ticket,
)

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
        passenger_resolver: PassengerResolver | None = None,
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
        # The resolver turns canonical passenger ids into full
        # :class:`Passenger` + :class:`Passport` records for the Amadeus
        # traveler block. ``None`` is accepted at construction but will
        # cause ``create`` to raise — callers must inject a resolver
        # before they book.
        self._passenger_resolver: PassengerResolver | None = passenger_resolver

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

        Pagination: ``criteria.max_results`` (default 50) is validated
        to lie in ``[1, 250]`` — 250 is the Amadeus Self-Service hard
        cap on a single request. Paging beyond 250 requires narrowing
        the query (date, cabin, airline whitelist) and is tracked as an
        open gap.

        Raises: any of the standard driver errors — see
        :meth:`FareSearchDriver.search`. Invalid ``max_results`` raises
        :class:`ValidationFailedError`.
        """
        max_results = getattr(criteria, "max_results", 50)
        if not (1 <= int(max_results) <= 250):
            raise ValidationFailedError(
                DRIVER_NAME,
                f"max_results must be between 1 and 250 (got {max_results!r}); "
                "Amadeus Self-Service rejects anything larger.",
            )
        params = criteria_to_query_params(criteria)
        params["max"] = str(int(max_results))
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
        # Defensive truncation — Amadeus usually honours ``max`` exactly,
        # but nothing guarantees the response stays at or below the cap.
        if len(fares) > int(max_results):
            fares = fares[: int(max_results)]
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
          3. Resolve ``passenger_ids`` via the injected
             :class:`PassengerResolver` and build authoritative Amadeus
             ``travelers`` blocks from the returned canonical
             :class:`Passenger` + :class:`Passport` records.
          4. POST ``/v1/booking/flight-orders`` and map the response
             through :func:`amadeus_order_to_pnr`.

        Raises :class:`PermanentError` on cache miss or when the driver
        was constructed without a resolver. Raises
        :class:`ValidationFailedError` when a resolved passenger is
        missing a field Amadeus treats as mandatory (date_of_birth).
        """
        if self._offer_cache is None:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create requires an offer cache; none was "
                "configured on this driver instance.",
            )
        if self._passenger_resolver is None:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create: driver constructed without "
                "passenger_resolver — cannot build real traveler blocks. "
                "Inject one via the constructor (the runtime bundle wires "
                "an InMemoryPassengerResolver by default).",
            )
        if not fare_ids:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create: fare_ids must not be empty.",
            )
        if not passenger_ids:
            raise PermanentError(
                DRIVER_NAME,
                "AmadeusDriver.create: passenger_ids must not be empty.",
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

        # Resolve canonical passengers and build real traveler blocks.
        passengers = await self._passenger_resolver.resolve(
            self._tenant_id, list(passenger_ids)
        )
        travelers_payload = [
            _passenger_to_traveler(idx, pax)
            for idx, pax in enumerate(passengers, start=1)
        ]

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


_GENDER_TO_AMADEUS: dict[Gender, str] = {
    Gender.MALE: "MALE",
    Gender.FEMALE: "FEMALE",
    Gender.UNSPECIFIED: "UNSPECIFIED",
}


def _split_e164(phone: str) -> tuple[str, str]:
    """Split an E.164 ``+CCNUMBER`` into ``(countryCallingCode, number)``.

    Amadeus phones are two separate fields; we don't need a library for
    this — E.164 is ``+`` then country code (1–3 digits) then subscriber
    number. We take the leading 1–3 digits as the country code, erring
    on the side of 2 when ambiguous since most of Voyagent's markets
    (India 91, UAE 971, UK 44, USA 1) are covered by 1–3-digit codes.
    """
    if not phone or not phone.startswith("+"):
        return ("", phone or "")
    digits = phone[1:]
    # Common cases: 1 (US/CA), 7 (RU/KZ). Otherwise use 2 or 3 digits —
    # 2 digits covers IN (91), UK (44), DE (49), FR (33), etc; 3 digits
    # covers AE (971), SG (65 is two), PH (63 is two)…for simplicity we
    # default to 2 digits unless the leading digit is 1 or 7.
    if digits[:1] in {"1", "7"}:
        cc, num = digits[:1], digits[1:]
    elif digits[:3] in {"971", "966", "974", "973", "880", "977"}:
        cc, num = digits[:3], digits[3:]
    else:
        cc, num = digits[:2], digits[2:]
    return (cc, num)


def _passenger_to_traveler(idx: int, passenger: Passenger) -> dict[str, Any]:
    """Map a canonical :class:`Passenger` to the Amadeus ``travelers[]`` shape.

    Amadeus requires ``id`` (1-indexed), ``dateOfBirth`` (ISO date),
    ``name.firstName`` / ``name.lastName``, ``gender``, and at least one
    contact channel. Passport data flows through ``documents[]`` when
    present.

    Raises :class:`ValidationFailedError` when ``date_of_birth`` is
    missing — Amadeus rejects the booking otherwise.
    """
    if passenger.date_of_birth is None:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"passenger {passenger.id} missing date_of_birth required for booking",
        )

    passport: Passport | None = passenger.passport
    # Name: passport MRZ wins when present (matches ticket issuance).
    if passport is not None:
        first_name = passport.given_name
        last_name = passport.family_name
    else:
        first_name = passenger.given_name
        last_name = passenger.family_name

    # Gender: passport > passenger > UNSPECIFIED.
    if passport is not None:
        gender_amadeus = _GENDER_TO_AMADEUS[passport.gender]
    elif passenger.gender is not None:
        gender_amadeus = _GENDER_TO_AMADEUS[passenger.gender]
    else:
        gender_amadeus = "UNSPECIFIED"

    traveler: dict[str, Any] = {
        "id": str(idx),
        "dateOfBirth": passenger.date_of_birth.isoformat(),
        "name": {"firstName": first_name, "lastName": last_name},
        "gender": gender_amadeus,
        # Round-trip the canonical id so audit records can join back.
        "meta": {"voyagent_passenger_id": str(passenger.id)},
    }

    # Contact block — Amadeus will 400 without at least a phone OR email.
    contact: dict[str, Any] = {}
    if passenger.emails:
        contact["emailAddress"] = passenger.emails[0].address
    if passenger.phones:
        phones_out: list[dict[str, Any]] = []
        for ph in passenger.phones:
            cc, num = _split_e164(ph.e164)
            phones_out.append(
                {
                    "deviceType": "MOBILE",
                    "countryCallingCode": cc,
                    "number": num,
                }
            )
        contact["phones"] = phones_out
    if contact:
        traveler["contact"] = contact

    # Documents: Amadeus accepts a PASSPORT document with number, issuing
    # country, expiry, and nationality.
    if passport is not None:
        traveler["documents"] = [
            {
                "documentType": "PASSPORT",
                "number": passport.number.get_secret_value(),
                "issuanceCountry": passport.issuing_country,
                "nationality": (
                    passenger.nationality or passport.issuing_country
                ),
                "expiryDate": passport.expiry_date.isoformat(),
                "holder": True,
                "birthPlace": passport.place_of_birth,
            }
        ]

    return traveler


__all__ = ["AmadeusDriver"]
