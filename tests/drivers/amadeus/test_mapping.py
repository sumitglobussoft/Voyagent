"""Pure-function tests for :mod:`drivers.amadeus.mapping`."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers._contracts.fare_search import FareSearchCriteria
from drivers.amadeus.mapping import (
    amadeus_offer_to_fares,
    amadeus_order_to_pnr,
    amadeus_segment_to_flight_segment,
    criteria_to_query_params,
)
from schemas.canonical import CabinClass, Money, PassengerType, PNRStatus, TaxRegime


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


# --------------------------------------------------------------------------- #
# amadeus_segment_to_flight_segment                                           #
# --------------------------------------------------------------------------- #


def test_segment_maps_core_fields() -> None:
    seg = {
        "departure": {"iataCode": "BOM", "at": "2026-05-10T09:00:00"},
        "arrival": {"iataCode": "DXB", "at": "2026-05-10T10:30:00"},
        "carrierCode": "EK",
        "number": "507",
        "aircraft": {"code": "77W"},
        "operating": {"carrierCode": "EK"},
    }
    tenant = _uuid7_like()
    result = amadeus_segment_to_flight_segment(seg, tenant)

    assert result.origin == "BOM"
    assert result.destination == "DXB"
    assert result.marketing_carrier == "EK"
    assert result.operating_carrier == "EK"
    assert result.flight_number == "507"
    assert result.aircraft == "77W"
    assert result.cabin == CabinClass.ECONOMY
    assert result.departure_at == datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)
    assert result.arrival_at == datetime(2026, 5, 10, 10, 30, tzinfo=timezone.utc)


def test_segment_missing_required_raises_validation() -> None:
    seg = {"carrierCode": "EK", "number": "507"}  # no departure/arrival
    with pytest.raises(ValidationFailedError) as exc:
        amadeus_segment_to_flight_segment(seg, _uuid7_like())
    assert exc.value.driver == "amadeus"


# --------------------------------------------------------------------------- #
# amadeus_offer_to_fares                                                      #
# --------------------------------------------------------------------------- #


def _offer(traveler_count: int = 1) -> dict:
    return {
        "id": "42",
        "lastTicketingDateTime": "2026-05-01T00:00:00",
        "travelerPricings": [
            {
                "travelerId": str(i + 1),
                "travelerType": "ADULT",
                "price": {
                    "currency": "USD",
                    "base": "300.00",
                    "total": "345.60",
                    "taxes": [
                        {"amount": "30.00", "code": "YQ"},
                        {"amount": "15.60", "code": "IN"},
                    ],
                    "fees": [{"amount": "0.00", "type": "SUPPLIER"}],
                },
            }
            for i in range(traveler_count)
        ],
    }


def test_offer_maps_to_one_fare_per_traveler() -> None:
    tenant = _uuid7_like()
    itinerary = _uuid7_like()
    pax = [_uuid7_like(), _uuid7_like()]
    fares = amadeus_offer_to_fares(_offer(2), pax, itinerary, tenant)
    assert len(fares) == 2
    for fare, pid in zip(fares, pax):
        assert fare.passenger_id == pid
        assert fare.itinerary_id == itinerary
        assert fare.tenant_id == tenant
        assert fare.source == "amadeus"
        assert fare.source_ref == "42"


def test_offer_totals_are_decimal_and_currencies_consistent() -> None:
    fares = amadeus_offer_to_fares(_offer(1), [_uuid7_like()], _uuid7_like(), _uuid7_like())
    f = fares[0]
    assert isinstance(f.base.amount, Decimal)
    assert f.base == Money(amount=Decimal("300.00"), currency="USD")
    assert f.total == Money(amount=Decimal("345.60"), currency="USD")
    assert {t.tax_amount.currency for t in f.taxes} == {"USD"}
    assert all(t.regime == TaxRegime.NONE for t in f.taxes)
    assert f.valid_until == datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def test_offer_passenger_id_count_mismatch_raises() -> None:
    with pytest.raises(ValidationFailedError):
        amadeus_offer_to_fares(_offer(2), [_uuid7_like()], _uuid7_like(), _uuid7_like())


# --------------------------------------------------------------------------- #
# amadeus_order_to_pnr                                                        #
# --------------------------------------------------------------------------- #


def _order(status: str = "CONFIRMED") -> dict:
    return {
        "id": "order-id-xyz",
        "status": status,
        "associatedRecords": [{"reference": "ABC123"}],
        "travelers": [{"id": "1"}],
        "flightOffers": [
            {
                "itineraries": [
                    {
                        "segments": [
                            {
                                "departure": {"iataCode": "BOM", "at": "2026-05-10T09:00:00"},
                                "arrival": {"iataCode": "DXB", "at": "2026-05-10T10:30:00"},
                                "carrierCode": "EK",
                                "number": "507",
                            }
                        ]
                    }
                ]
            }
        ],
        "ticketingAgreement": {"dateTime": "2026-04-30T23:59:00"},
    }


@pytest.mark.parametrize(
    "amadeus_status, expected",
    [
        ("CONFIRMED", PNRStatus.CONFIRMED),
        ("TICKETED", PNRStatus.TICKETED),
        ("CANCELLED", PNRStatus.CANCELLED),
        ("SCHEDULE_CHANGE", PNRStatus.SCHEDULE_CHANGE),
        ("HELD", PNRStatus.CONFIRMED),
        ("SOMETHING_NEW", PNRStatus.CONFIRMED),  # fallback branch
    ],
)
def test_order_status_mapping(amadeus_status: str, expected: PNRStatus) -> None:
    pnr = amadeus_order_to_pnr(_order(amadeus_status), tenant_id=_uuid7_like())
    assert pnr.status is expected


def test_order_maps_locator_and_source_ref() -> None:
    pnr = amadeus_order_to_pnr(_order(), tenant_id=_uuid7_like())
    assert pnr.locator == "ABC123"
    assert pnr.source_ref == "order-id-xyz"
    assert pnr.source == "amadeus"
    assert pnr.ticket_time_limit == datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc)


def test_order_without_segments_raises() -> None:
    order = _order()
    order["flightOffers"] = []
    with pytest.raises(ValidationFailedError):
        amadeus_order_to_pnr(order, tenant_id=_uuid7_like())


# --------------------------------------------------------------------------- #
# criteria_to_query_params                                                    #
# --------------------------------------------------------------------------- #


def _criteria(**overrides) -> FareSearchCriteria:
    base = dict(
        passengers={PassengerType.ADULT: 1},
        origin="BOM",
        destination="DXB",
        outbound_date=date(2026, 5, 10),
    )
    base.update(overrides)
    return FareSearchCriteria(**base)


def test_criteria_one_way() -> None:
    params = criteria_to_query_params(_criteria())
    assert params["originLocationCode"] == "BOM"
    assert params["destinationLocationCode"] == "DXB"
    assert params["departureDate"] == "2026-05-10"
    assert params["adults"] == "1"
    assert params["travelClass"] == "ECONOMY"
    assert params["nonStop"] == "false"
    assert "returnDate" not in params


def test_criteria_round_trip_and_cabin() -> None:
    params = criteria_to_query_params(
        _criteria(return_date=date(2026, 5, 20), cabin=CabinClass.BUSINESS)
    )
    assert params["returnDate"] == "2026-05-20"
    assert params["travelClass"] == "BUSINESS"


def test_criteria_direct_only_and_mixed_pax() -> None:
    params = criteria_to_query_params(
        _criteria(
            passengers={PassengerType.ADULT: 2, PassengerType.CHILD: 1, PassengerType.INFANT: 1},
            direct_only=True,
        )
    )
    assert params["nonStop"] == "true"
    assert params["adults"] == "2"
    assert params["children"] == "1"
    assert params["infants"] == "1"


def test_criteria_airline_whitelist_and_blacklist() -> None:
    params = criteria_to_query_params(
        _criteria(airline_whitelist=["EK", "QR"], airline_blacklist=["AI"])
    )
    assert params["includedAirlineCodes"] == "EK,QR"
    assert params["excludedAirlineCodes"] == "AI"


def test_criteria_max_price_sets_currency_and_cap() -> None:
    params = criteria_to_query_params(
        _criteria(max_price=Money(amount=Decimal("500"), currency="AED"))
    )
    assert params["currencyCode"] == "AED"
    assert params["maxPrice"] == "500"
