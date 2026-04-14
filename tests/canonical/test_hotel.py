"""Tests for the canonical hotel model expansion.

Covers BoardBasis enum, HotelRoom / HotelRate / HotelProperty validation,
HotelSearchResult date invariants, and HotelBooking currency round-trip.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.canonical import (
    BoardBasis,
    HotelBooking,
    HotelBookingStatus,
    HotelProperty,
    HotelRate,
    HotelRoom,
    HotelSearchResult,
    LocalizedText,
    Money,
)


def _make_room(**overrides) -> HotelRoom:
    base = dict(
        code="DLX",
        name="Deluxe King",
        board_basis=BoardBasis.BB,
        max_occupancy=2,
        bed_type="king",
    )
    base.update(overrides)
    return HotelRoom(**base)


def _make_rate(**overrides) -> HotelRate:
    base = dict(
        room=_make_room(),
        price=Money(amount=Decimal("12500.00"), currency="INR"),
        cancellation_policy=LocalizedText(default="Free cancellation until 48h prior."),
        is_refundable=True,
        rate_key="rk-abc-123",
    )
    base.update(overrides)
    return HotelRate(**base)


def _make_property(**overrides) -> HotelProperty:
    base = dict(
        id="tbo-1001",
        name="Taj Palace",
        address="Chanakyapuri, New Delhi",
        city="DEL",
        country="IN",
        latitude=28.59,
        longitude=77.17,
        star_rating=5,
        amenities=["pool", "spa"],
        images=["https://example.com/a.jpg"],
    )
    base.update(overrides)
    return HotelProperty(**base)


class TestHotelRoom:
    def test_defaults_to_room_only_board_basis(self) -> None:
        room = HotelRoom(code="STD", name="Standard", max_occupancy=2)
        assert room.board_basis is BoardBasis.RO

    def test_max_occupancy_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            HotelRoom(code="STD", name="Standard", max_occupancy=0)

    def test_board_basis_rejects_unknown_token(self) -> None:
        with pytest.raises(ValidationError):
            HotelRoom(
                code="STD",
                name="Standard",
                max_occupancy=1,
                board_basis="LUNCH",  # type: ignore[arg-type]
            )


class TestHotelRate:
    def test_rate_key_is_required(self) -> None:
        with pytest.raises(ValidationError):
            HotelRate(
                room=_make_room(),
                price=Money(amount=Decimal("1"), currency="INR"),
            )  # type: ignore[call-arg]

    def test_money_round_trip_preserves_currency(self) -> None:
        rate = _make_rate()
        dumped = rate.model_dump(mode="json")
        reloaded = HotelRate.model_validate(dumped)
        assert reloaded.price.currency == "INR"
        assert reloaded.price.amount == Decimal("12500.00")


class TestHotelProperty:
    def test_star_rating_bounds(self) -> None:
        with pytest.raises(ValidationError):
            _make_property(star_rating=7)

    def test_latitude_bounds(self) -> None:
        with pytest.raises(ValidationError):
            _make_property(latitude=200.0)


class TestHotelSearchResult:
    def test_check_out_must_follow_check_in(self) -> None:
        with pytest.raises(ValidationError, match="check_out must be after check_in"):
            HotelSearchResult(
                property=_make_property(),
                rates=[_make_rate()],
                check_in=date(2026, 5, 10),
                check_out=date(2026, 5, 10),
                guest_count=2,
            )

    def test_happy_path(self) -> None:
        result = HotelSearchResult(
            property=_make_property(),
            rates=[_make_rate()],
            check_in=date(2026, 5, 10),
            check_out=date(2026, 5, 12),
            guest_count=2,
        )
        assert result.property.country == "IN"
        assert result.rates[0].room.board_basis is BoardBasis.BB


class TestHotelBooking:
    def test_round_trips_with_new_fields(self) -> None:
        now = datetime(2026, 4, 14, tzinfo=timezone.utc)
        booking = HotelBooking(
            id="00000000-0000-7000-8000-000000000001",
            tenant_id="00000000-0000-7000-8000-0000000000aa",
            stay_id="00000000-0000-7000-8000-0000000000bb",
            supplier="tbo",
            supplier_ref="TBO-42",
            status=HotelBookingStatus.PENDING,
            cost=Money(amount=Decimal("12500.00"), currency="INR"),
            currency="INR",
            passenger_ids=["00000000-0000-7000-8000-0000000000cc"],
            selected_rate_key="rk-abc-123",
            created_at=now,
            updated_at=now,
        )
        assert booking.status is HotelBookingStatus.PENDING
        assert booking.selected_rate_key == "rk-abc-123"
        assert booking.cost.currency == "INR"
