"""Tests for schemas.canonical.travel.

Covers FlightSegment time/flight-number invariants, HotelStay date math, and
Fare currency consistency. JournalEntry is tested in test_finance.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Callable

import pytest
from pydantic import ValidationError

from schemas.canonical import (
    CabinClass,
    Fare,
    FareComponent,
    FlightSegment,
    HotelStay,
    Money,
    TaxLine,
    TaxRegime,
)


# --------------------------------------------------------------------------- #
# FlightSegment                                                               #
# --------------------------------------------------------------------------- #


def _flight_kwargs(flight_id: str) -> dict:
    return dict(
        id=flight_id,
        marketing_carrier="AI",
        flight_number="101",
        origin="BLR",
        destination="DXB",
        departure_at=datetime(2026, 5, 1, 2, 0, 0, tzinfo=timezone.utc),
        arrival_at=datetime(2026, 5, 1, 5, 0, 0, tzinfo=timezone.utc),
        cabin=CabinClass.ECONOMY,
    )


class TestFlightSegment:
    def test_arrival_must_be_after_departure(self, make_entity_id: Callable[[], str]) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["arrival_at"] = kwargs["departure_at"]
        with pytest.raises(ValidationError, match="arrival_at must be after departure_at"):
            FlightSegment(**kwargs)

    def test_arrival_before_departure_raises(self, make_entity_id: Callable[[], str]) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["arrival_at"] = kwargs["departure_at"] - timedelta(hours=1)
        with pytest.raises(ValidationError, match="arrival_at must be after departure_at"):
            FlightSegment(**kwargs)

    def test_rejects_naive_departure(self, make_entity_id: Callable[[], str]) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["departure_at"] = datetime(2026, 5, 1, 2, 0, 0)
        with pytest.raises(ValidationError, match="timezone-aware"):
            FlightSegment(**kwargs)

    def test_rejects_naive_arrival(self, make_entity_id: Callable[[], str]) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["arrival_at"] = datetime(2026, 5, 1, 5, 0, 0)
        with pytest.raises(ValidationError, match="timezone-aware"):
            FlightSegment(**kwargs)

    def test_non_utc_aware_datetimes_are_normalized(self, make_entity_id: Callable[[], str]) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["departure_at"] = datetime(2026, 5, 1, 7, 30, 0, tzinfo=ist)  # 02:00 UTC
        kwargs["arrival_at"] = datetime(2026, 5, 1, 10, 30, 0, tzinfo=ist)   # 05:00 UTC
        seg = FlightSegment(**kwargs)
        assert seg.departure_at.utcoffset() == timedelta(0)
        assert seg.arrival_at.utcoffset() == timedelta(0)

    @pytest.mark.parametrize("good_number", ["1", "101", "9999", "101A", "9W"])
    def test_accepts_valid_flight_numbers(
        self, make_entity_id: Callable[[], str], good_number: str
    ) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["flight_number"] = good_number
        seg = FlightSegment(**kwargs)
        assert seg.flight_number == good_number

    @pytest.mark.parametrize(
        "bad_number",
        [
            "",           # empty
            "AI101",      # alpha prefix
            "12345",      # 5 digits
            "101AB",      # two trailing letters
            "10 1",       # whitespace
            "a101",       # lowercase
        ],
    )
    def test_rejects_bad_flight_numbers(
        self, make_entity_id: Callable[[], str], bad_number: str
    ) -> None:
        kwargs = _flight_kwargs(make_entity_id())
        kwargs["flight_number"] = bad_number
        with pytest.raises(ValidationError):
            FlightSegment(**kwargs)


# --------------------------------------------------------------------------- #
# HotelStay                                                                   #
# --------------------------------------------------------------------------- #


class TestHotelStay:
    def test_check_out_must_be_after_check_in(self, make_entity_id: Callable[[], str]) -> None:
        with pytest.raises(ValidationError, match="check_out must be after check_in"):
            HotelStay(
                id=make_entity_id(),
                property_name="Hotel Taj",
                address_country="IN",
                check_in=date(2026, 6, 1),
                check_out=date(2026, 6, 1),  # equal
                nights=1,
                guest_count=2,
            )

    def test_check_out_before_check_in_raises(self, make_entity_id: Callable[[], str]) -> None:
        with pytest.raises(ValidationError, match="check_out must be after check_in"):
            HotelStay(
                id=make_entity_id(),
                property_name="Hotel Taj",
                address_country="IN",
                check_in=date(2026, 6, 5),
                check_out=date(2026, 6, 1),
                nights=1,
                guest_count=2,
            )

    def test_nights_must_match_date_range(self, make_entity_id: Callable[[], str]) -> None:
        # 4-night range but claiming 3 nights.
        with pytest.raises(ValidationError, match="does not match check-in/out range"):
            HotelStay(
                id=make_entity_id(),
                property_name="Hotel Taj",
                address_country="IN",
                check_in=date(2026, 6, 1),
                check_out=date(2026, 6, 5),
                nights=3,
                guest_count=2,
            )

    def test_matching_nights_and_range_is_valid(self, make_entity_id: Callable[[], str]) -> None:
        stay = HotelStay(
            id=make_entity_id(),
            property_name="Hotel Taj",
            address_country="IN",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            nights=4,
            guest_count=2,
        )
        assert stay.nights == 4


# --------------------------------------------------------------------------- #
# Fare                                                                        #
# --------------------------------------------------------------------------- #


class TestFareCurrencyConsistency:
    def test_fare_with_consistent_currency_is_valid(self, make_entity_id: Callable[[], str]) -> None:
        fare = Fare(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            itinerary_id=make_entity_id(),
            passenger_id=make_entity_id(),
            base=Money(amount=Decimal("10000"), currency="INR"),
            fees=[
                FareComponent(label="YQ", amount=Money(amount=Decimal("500"), currency="INR")),
                FareComponent(label="agency_markup", amount=Money(amount=Decimal("200"), currency="INR")),
            ],
            taxes=[
                TaxLine(
                    regime=TaxRegime.GST_INDIA,
                    code="CGST",
                    rate_bps=900,
                    taxable_amount=Money(amount=Decimal("10700"), currency="INR"),
                    tax_amount=Money(amount=Decimal("963"), currency="INR"),
                ),
            ],
            total=Money(amount=Decimal("11663"), currency="INR"),
            source="amadeus",
        )
        assert fare.total.currency == "INR"

    def test_fare_base_and_total_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            Fare(
                id=make_entity_id(),
                tenant_id=make_entity_id(),
                itinerary_id=make_entity_id(),
                passenger_id=make_entity_id(),
                base=Money(amount=Decimal("10000"), currency="INR"),
                total=Money(amount=Decimal("120"), currency="USD"),
                source="amadeus",
            )

    def test_fare_fee_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            Fare(
                id=make_entity_id(),
                tenant_id=make_entity_id(),
                itinerary_id=make_entity_id(),
                passenger_id=make_entity_id(),
                base=Money(amount=Decimal("10000"), currency="INR"),
                fees=[
                    FareComponent(
                        label="YQ",
                        amount=Money(amount=Decimal("5"), currency="USD"),
                    ),
                ],
                total=Money(amount=Decimal("10000"), currency="INR"),
                source="amadeus",
            )

    def test_fare_tax_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            Fare(
                id=make_entity_id(),
                tenant_id=make_entity_id(),
                itinerary_id=make_entity_id(),
                passenger_id=make_entity_id(),
                base=Money(amount=Decimal("10000"), currency="INR"),
                taxes=[
                    TaxLine(
                        regime=TaxRegime.VAT_UAE,
                        code="VAT",
                        rate_bps=500,
                        taxable_amount=Money(amount=Decimal("10000"), currency="AED"),
                        tax_amount=Money(amount=Decimal("500"), currency="AED"),
                    ),
                ],
                total=Money(amount=Decimal("10500"), currency="INR"),
                source="amadeus",
            )
