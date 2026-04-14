"""Amadeus JSON -> Voyagent canonical mapping.

These are the heart of the driver: pure functions, no I/O, heavily typed.
Anything that couldn't be mapped (missing required field, unparseable date,
shape drift) raises :class:`ValidationFailedError` with ``driver="amadeus"``.

All monetary values are parsed through ``Decimal(str(...))`` so we never
round-trip through float. All datetimes are forced to timezone-aware UTC;
Amadeus returns local-to-origin times without an offset, which we currently
pin to UTC with a TODO for proper timezone resolution (see module docstring
of :mod:`drivers.amadeus`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from drivers._contracts.errors import ValidationFailedError
from drivers._contracts.fare_search import FareSearchCriteria
from schemas.canonical import (
    CabinClass,
    EntityId,
    Fare,
    FareComponent,
    FlightSegment,
    IATACode,
    Money,
    PassengerType,
    PNR,
    PNRStatus,
    SegmentStatus,
    TaxLine,
    TaxRegime,
)

logger = logging.getLogger(__name__)

DRIVER_NAME = "amadeus"

# --------------------------------------------------------------------------- #
# Enum maps                                                                   #
# --------------------------------------------------------------------------- #

_AMADEUS_CABIN_TO_CANONICAL: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}

_CANONICAL_CABIN_TO_AMADEUS: dict[CabinClass, str] = {v: k for k, v in _AMADEUS_CABIN_TO_CANONICAL.items()}

_PASSENGER_TYPE_TO_AMADEUS: dict[PassengerType, str] = {
    PassengerType.ADULT: "ADULT",
    PassengerType.CHILD: "CHILD",
    PassengerType.INFANT: "HELD_INFANT",
    PassengerType.SENIOR: "SENIOR",
}

# Amadeus order status strings observed in Self-Service booking docs.
_ORDER_STATUS_TO_PNR: dict[str, PNRStatus] = {
    "CONFIRMED": PNRStatus.CONFIRMED,
    "HK": PNRStatus.CONFIRMED,
    "HELD": PNRStatus.CONFIRMED,
    "TICKETED": PNRStatus.TICKETED,
    "CANCELLED": PNRStatus.CANCELLED,
    "XX": PNRStatus.CANCELLED,
    "SCHEDULE_CHANGE": PNRStatus.SCHEDULE_CHANGE,
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _new_entity_id() -> EntityId:
    """Generate a UUIDv7-shaped string.

    Python's stdlib does not ship UUIDv7; until the runtime helper lands we
    synthesise one by patching the version nibble onto a uuid4. Only used for
    driver-materialized records that don't carry a vendor id; tests treat the
    id as opaque.
    """
    raw = uuid.uuid4()
    # Force version 7 nibble + RFC-4122 variant bits.
    as_int = raw.int
    as_int &= ~(0xF << 76)
    as_int |= 0x7 << 76
    as_int &= ~(0xC << 62)
    as_int |= 0x8 << 62
    return str(uuid.UUID(int=as_int))


def _require(obj: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in obj or obj[key] in (None, ""):
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus {ctx}: missing required field '{key}'.",
        )
    return obj[key]


def _parse_decimal(value: Any, ctx: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus {ctx}: cannot parse decimal from {value!r}.",
        ) from exc


def _parse_datetime(value: Any, ctx: str) -> datetime:
    """Parse Amadeus ISO8601 strings.

    Amadeus returns local-to-origin times without a timezone offset
    (e.g. ``2024-08-12T14:30:00``). Canonical FlightSegment requires
    timezone-aware UTC — we attach UTC here as a v0 compromise. A real
    production driver must resolve the airport timezone and convert.

    TODO(voyagent-amadeus): airport-timezone resolution. Either call
    the ``/v1/reference-data/locations/airports`` endpoint and cache, or
    push timezone awareness to the agent layer that owns a richer
    airport registry.
    """
    if not isinstance(value, str):
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus {ctx}: datetime must be a string, got {type(value).__name__}.",
        )
    try:
        # ``fromisoformat`` in 3.12 handles most ISO-8601 shapes including
        # 'Z' suffix; Amadeus omits the offset altogether.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus {ctx}: cannot parse datetime {value!r}.",
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iata(value: Any, ctx: str) -> IATACode:
    if not isinstance(value, str) or not value:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus {ctx}: expected IATA code string, got {value!r}.",
        )
    upper = value.upper()
    return upper  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Segments                                                                    #
# --------------------------------------------------------------------------- #


def amadeus_segment_to_flight_segment(seg: dict[str, Any], tenant_id: EntityId) -> FlightSegment:
    """Map one ``itineraries[].segments[]`` entry to canonical :class:`FlightSegment`.

    Cabin is resolved per-traveler on Amadeus (``travelerPricings[].fareDetailsBySegment[].cabin``)
    so this function does not know the cabin without extra context. Callers
    that know the cabin should overwrite the field; otherwise this default
    uses ECONOMY and records the Amadeus RBD in ``booking_class`` when set.
    """
    try:
        departure = _require(seg, "departure", "segment")
        arrival = _require(seg, "arrival", "segment")
        number = str(_require(seg, "number", "segment"))
        marketing = _iata(_require(seg, "carrierCode", "segment"), "segment.carrierCode")
    except ValidationFailedError:
        raise

    operating_raw = seg.get("operating") or {}
    operating = operating_raw.get("carrierCode") if isinstance(operating_raw, dict) else None

    aircraft_raw = seg.get("aircraft") or {}
    aircraft = aircraft_raw.get("code") if isinstance(aircraft_raw, dict) else None

    return FlightSegment(
        id=_new_entity_id(),
        marketing_carrier=marketing,
        operating_carrier=_iata(operating, "segment.operating") if operating else None,
        flight_number=number,
        origin=_iata(_require(departure, "iataCode", "segment.departure"), "segment.departure.iataCode"),
        destination=_iata(_require(arrival, "iataCode", "segment.arrival"), "segment.arrival.iataCode"),
        departure_at=_parse_datetime(_require(departure, "at", "segment.departure"), "segment.departure.at"),
        arrival_at=_parse_datetime(_require(arrival, "at", "segment.arrival"), "segment.arrival.at"),
        cabin=CabinClass.ECONOMY,
        aircraft=str(aircraft) if aircraft else None,
        status=SegmentStatus.PLANNED,
    )


# --------------------------------------------------------------------------- #
# Fares                                                                       #
# --------------------------------------------------------------------------- #


def _money(amount: Any, currency: str, ctx: str) -> Money:
    return Money(amount=_parse_decimal(amount, ctx), currency=currency.upper())


def amadeus_offer_to_fares(
    offer: dict[str, Any],
    passenger_ids: list[EntityId],
    itinerary_id: EntityId,
    tenant_id: EntityId,
) -> list[Fare]:
    """Map one Amadeus flight-offer to N canonical :class:`Fare` records.

    One Fare is produced per entry in ``travelerPricings`` (typically one
    per passenger). ``passenger_ids`` must line up positionally with
    ``travelerPricings`` — the caller is responsible for that alignment
    based on its passenger-to-traveler mapping.

    ``taxes`` are populated from Amadeus's per-traveler fare breakdown.
    Self-Service does not disclose the tax regime (VAT vs sales tax vs
    YQ/YR surcharge), so every :class:`TaxLine` is emitted with
    ``TaxRegime.NONE`` and the Amadeus tax ``code`` as-is. A tax-aware
    enterprise driver would classify these at this layer.
    """
    offer_id = str(_require(offer, "id", "offer"))
    travelers = offer.get("travelerPricings") or []
    if not isinstance(travelers, list) or not travelers:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus offer {offer_id}: travelerPricings missing or empty.",
        )
    if len(passenger_ids) != len(travelers):
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus offer {offer_id}: expected {len(travelers)} passenger_ids, "
            f"got {len(passenger_ids)}.",
        )

    valid_until = offer.get("lastTicketingDateTime")
    valid_until_dt = _parse_datetime(valid_until, "offer.lastTicketingDateTime") if valid_until else None

    fares: list[Fare] = []
    for pax_id, tp in zip(passenger_ids, travelers, strict=True):
        if not isinstance(tp, dict):
            raise ValidationFailedError(
                DRIVER_NAME, f"Amadeus offer {offer_id}: travelerPricing is not an object."
            )
        price = _require(tp, "price", f"offer {offer_id}.travelerPricings.price")
        currency = str(_require(price, "currency", "price.currency")).upper()
        base_amount = _parse_decimal(_require(price, "base", "price.base"), "price.base")
        total_amount = _parse_decimal(_require(price, "total", "price.total"), "price.total")

        taxes: list[TaxLine] = []
        for tax in price.get("taxes") or []:
            if not isinstance(tax, dict):
                continue
            tax_amount = _parse_decimal(
                tax.get("amount", "0"), f"offer {offer_id}.tax.amount"
            )
            taxes.append(
                TaxLine(
                    regime=TaxRegime.NONE,
                    code=str(tax.get("code") or "TAX"),
                    rate_bps=0,
                    taxable_amount=Money(amount=base_amount, currency=currency),
                    tax_amount=Money(amount=tax_amount, currency=currency),
                )
            )

        fees: list[FareComponent] = []
        for fee in price.get("fees") or []:
            if not isinstance(fee, dict):
                continue
            fee_amount = _parse_decimal(fee.get("amount", "0"), f"offer {offer_id}.fee.amount")
            if fee_amount == 0:
                continue
            fees.append(
                FareComponent(
                    label=str(fee.get("type") or "FEE"),
                    amount=Money(amount=fee_amount, currency=currency),
                )
            )

        fares.append(
            Fare(
                id=_new_entity_id(),
                tenant_id=tenant_id,
                itinerary_id=itinerary_id,
                passenger_id=pax_id,
                base=Money(amount=base_amount, currency=currency),
                fees=fees,
                taxes=taxes,
                total=Money(amount=total_amount, currency=currency),
                source=DRIVER_NAME,
                source_ref=offer_id,
                valid_until=valid_until_dt,
            )
        )

    return fares


# --------------------------------------------------------------------------- #
# PNR                                                                         #
# --------------------------------------------------------------------------- #


def amadeus_order_to_pnr(order: dict[str, Any], tenant_id: EntityId) -> PNR:
    """Map an Amadeus ``flight-orders`` resource to canonical :class:`PNR`.

    Amadeus exposes two identifiers:
      * ``id`` — the order id used on GET/DELETE paths,
      * ``associatedRecords[].reference`` — the airline/GDS record locator
        (the thing travelers quote over the phone).

    We use the order id as ``source_ref`` and the record-locator reference
    as the canonical ``locator``.
    """
    order_id = str(_require(order, "id", "order"))

    associated = order.get("associatedRecords") or []
    locator: str | None = None
    if isinstance(associated, list):
        for rec in associated:
            if isinstance(rec, dict) and rec.get("reference"):
                locator = str(rec["reference"])
                break
    if not locator:
        # Some sandbox responses omit associatedRecords. Fall back to order id
        # so we still produce a valid PNR (the contract requires locator).
        locator = order_id

    raw_status = str(order.get("status") or order.get("orderStatus") or "CONFIRMED").upper()
    status = _ORDER_STATUS_TO_PNR.get(raw_status, PNRStatus.CONFIRMED)

    travelers = order.get("travelers") or []
    if not isinstance(travelers, list) or not travelers:
        raise ValidationFailedError(
            DRIVER_NAME, f"Amadeus order {order_id}: travelers missing or empty."
        )
    passenger_ids: list[EntityId] = [_new_entity_id() for _ in travelers]

    # Amadeus order embeds flightOffers[*].itineraries[*].segments
    flight_offers = order.get("flightOffers") or []
    segment_ids: list[EntityId] = []
    for offer in flight_offers:
        for itin in (offer or {}).get("itineraries") or []:
            for seg in (itin or {}).get("segments") or []:
                segment_ids.append(_new_entity_id())
    if not segment_ids:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Amadeus order {order_id}: no segments found in flightOffers.",
        )

    ticket_time_limit: datetime | None = None
    ttl_raw = (
        order.get("ticketingAgreement", {}).get("dateTime")
        if isinstance(order.get("ticketingAgreement"), dict)
        else None
    )
    if ttl_raw:
        ticket_time_limit = _parse_datetime(ttl_raw, "order.ticketingAgreement.dateTime")

    now = datetime.now(timezone.utc)
    return PNR(
        id=_new_entity_id(),
        tenant_id=tenant_id,
        locator=locator,
        source=DRIVER_NAME,
        source_ref=order_id,
        status=status,
        passenger_ids=passenger_ids,
        segment_ids=segment_ids,
        fare_ids=[],
        ticket_time_limit=ticket_time_limit,
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# Criteria                                                                    #
# --------------------------------------------------------------------------- #


def criteria_to_query_params(criteria: FareSearchCriteria) -> dict[str, str]:
    """Build the query string for ``GET /v2/shopping/flight-offers``.

    Amadeus uses a single numeric ``adults`` / ``children`` / ``infants``
    tuple plus a ``travelClass`` enum. Whitelist/blacklist map to
    ``includedAirlineCodes`` / ``excludedAirlineCodes`` (comma-joined).
    """
    params: dict[str, str] = {
        "originLocationCode": criteria.origin,
        "destinationLocationCode": criteria.destination,
        "departureDate": criteria.outbound_date.isoformat(),
        "travelClass": _CANONICAL_CABIN_TO_AMADEUS[criteria.cabin],
        "currencyCode": criteria.max_price.currency if criteria.max_price else "USD",
        "nonStop": "true" if criteria.direct_only else "false",
    }
    if criteria.return_date is not None:
        params["returnDate"] = criteria.return_date.isoformat()

    adults = criteria.passengers.get(PassengerType.ADULT, 0)
    children = criteria.passengers.get(PassengerType.CHILD, 0)
    infants = criteria.passengers.get(PassengerType.INFANT, 0)
    seniors = criteria.passengers.get(PassengerType.SENIOR, 0)
    # Amadeus treats seniors as adults for pricing purposes.
    params["adults"] = str(adults + seniors if (adults + seniors) > 0 else max(adults, 1))
    if children:
        params["children"] = str(children)
    if infants:
        params["infants"] = str(infants)

    if criteria.airline_whitelist:
        params["includedAirlineCodes"] = ",".join(criteria.airline_whitelist)
    if criteria.airline_blacklist:
        params["excludedAirlineCodes"] = ",".join(criteria.airline_blacklist)
    if criteria.max_price is not None:
        # Amadeus expects an integer maxPrice; we floor via int(Decimal).
        params["maxPrice"] = str(int(criteria.max_price.amount))

    return params


__all__ = [
    "amadeus_offer_to_fares",
    "amadeus_order_to_pnr",
    "amadeus_segment_to_flight_segment",
    "criteria_to_query_params",
]
