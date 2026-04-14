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
    ) -> None:
        self._config = config
        self._client = client or AmadeusClient(config)
        # tenant_id is required to materialize canonical records; we let
        # callers supply a synthetic id when not in a multi-tenant context
        # (e.g. tests, scripts).
        self._tenant_id: EntityId = tenant_id or _new_entity_id()

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
                "create": "requires_offer_cache",
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
            fares.extend(
                amadeus_offer_to_fares(
                    offer,
                    passenger_ids=pax_slice,
                    itinerary_id=itinerary_id,
                    tenant_id=self._tenant_id,
                )
            )

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
        """Create a flight-order.

        **v0 limitation.** Amadeus Self-Service requires the agent to POST
        the full original flight-offer JSON (re-priced via
        ``/v1/shopping/flight-offers/pricing``) along with traveler details.
        This Protocol signature only receives canonical ``fare_ids`` and
        ``passenger_ids`` — the vendor-native offer body must be sourced
        from Voyagent's offer cache, which is a future runtime concern.

        Until the cache exists, ``create`` raises :class:`PermanentError`.
        A real implementation will:
          1. look up the cached Amadeus offer by ``fare_ids``,
          2. fetch canonical Passengers by ``passenger_ids`` and convert
             them to Amadeus ``travelers`` blocks,
          3. POST ``/v1/booking/flight-orders`` with that body,
          4. map the response through :func:`amadeus_order_to_pnr`.
        """
        raise PermanentError(
            DRIVER_NAME,
            "AmadeusDriver.create requires the original offer JSON, which the "
            "Voyagent offer cache does not yet expose. Re-pricing + booking "
            "will be wired when the runtime offer cache lands.",
        )

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


__all__ = ["AmadeusDriver"]
