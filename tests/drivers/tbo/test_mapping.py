"""Pure-function tests for the TBO response mappers.

Covers ``_parse_search_offers``, ``_parse_search_results``, and
``_parse_rate_entry`` edge cases (missing fields, non-refundable rates,
currency fallbacks). These are deliberately called from the module's
internal surface so the mapping logic is pinned independently from the
driver's HTTP orchestration.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers._contracts.hotel_search import HotelSearchCriteria
from drivers.tbo.driver import (
    _parse_board_basis,
    _parse_rate,
    _parse_rate_entry,
    _parse_search_offers,
    _parse_search_results,
)
from schemas.canonical import BoardBasis


def _criteria() -> HotelSearchCriteria:
    return HotelSearchCriteria(
        destination_country="IN",
        destination_city="DEL",
        check_in=date(2026, 5, 10),
        check_out=date(2026, 5, 12),
        guest_count=2,
    )


# --------------------------------------------------------------------------- #
# _parse_search_offers                                                        #
# --------------------------------------------------------------------------- #


def test_parse_search_offers_empty_payload_returns_empty_list() -> None:
    assert _parse_search_offers({}) == []
    assert _parse_search_offers({"HotelSearchResult": {}}) == []
    assert _parse_search_offers({"HotelSearchResult": {"HotelResults": []}}) == []


def test_parse_search_offers_non_dict_returns_empty_list() -> None:
    assert _parse_search_offers("nope") == []
    assert _parse_search_offers(None) == []
    assert _parse_search_offers([1, 2]) == []


def test_parse_search_offers_uses_top_level_currency_fallback() -> None:
    payload = {
        "Currency": "INR",
        "HotelSearchResult": {
            "HotelResults": [
                {
                    "HotelCode": "H-1",
                    "HotelName": "No-Currency Hotel",
                    "CountryCode": "IN",
                    "Rooms": [{"TotalFare": "1000.00"}],
                }
            ]
        },
    }
    offers = _parse_search_offers(payload)
    assert len(offers) == 1
    assert offers[0].cost.currency == "INR"
    assert offers[0].cost.amount == Decimal("1000.00")


def test_parse_search_offers_defaults_missing_hotel_fields() -> None:
    payload = {
        "HotelSearchResult": {
            "HotelResults": [
                {"Rooms": [{"TotalFare": "250.00", "Currency": "USD"}]}
            ]
        },
    }
    offers = _parse_search_offers(payload)
    assert len(offers) == 1
    assert offers[0].property_name == "Unknown hotel"
    assert offers[0].address_country == "XX"
    assert offers[0].cancellation_text.default.startswith("See supplier")


def test_parse_search_offers_skips_room_with_bad_price() -> None:
    payload = {
        "HotelSearchResult": {
            "HotelResults": [
                {
                    "HotelCode": "H-X",
                    "HotelName": "Bad Price",
                    "Rooms": [{"TotalFare": "not-a-number"}],
                }
            ]
        },
    }
    assert _parse_search_offers(payload) == []


def test_parse_search_offers_prefers_totalfare_over_price() -> None:
    payload = {
        "HotelSearchResult": {
            "HotelResults": [
                {
                    "HotelCode": "H-2",
                    "HotelName": "TwoFares",
                    "Rooms": [
                        {
                            "TotalFare": "500.00",
                            "Price": "999.00",
                            "Currency": "USD",
                        }
                    ],
                }
            ]
        },
    }
    offers = _parse_search_offers(payload)
    assert offers[0].cost.amount == Decimal("500.00")


# --------------------------------------------------------------------------- #
# _parse_search_results                                                       #
# --------------------------------------------------------------------------- #


def test_parse_search_results_skips_hotels_with_no_priced_rooms() -> None:
    payload = {
        "HotelSearchResult": {
            "HotelResults": [
                {
                    "HotelCode": "H-NP",
                    "HotelName": "No-Price",
                    "Rooms": [{"Name": "Standard"}],  # no price field
                }
            ]
        },
    }
    assert _parse_search_results(payload, _criteria()) == []


def test_parse_search_results_maps_star_rating_and_geo() -> None:
    payload = {
        "HotelSearchResult": {
            "HotelResults": [
                {
                    "HotelCode": "H-42",
                    "HotelName": "Geo Hotel",
                    "CityName": "Delhi",
                    "CountryCode": "IN",
                    "HotelRating": "5",
                    "Latitude": "28.61",
                    "Longitude": "77.21",
                    "HotelFacilities": ["spa"],
                    "Images": ["http://example.com/x.jpg"],
                    "Rooms": [
                        {
                            "Name": "Suite",
                            "TotalFare": "12000",
                            "Currency": "INR",
                            "BookingCode": "rk-1",
                            "MealType": "Breakfast",
                        }
                    ],
                }
            ]
        }
    }
    results = _parse_search_results(payload, _criteria())
    assert len(results) == 1
    prop = results[0].property
    assert prop.star_rating == 5
    assert prop.latitude == pytest.approx(28.61)
    assert prop.longitude == pytest.approx(77.21)
    assert prop.amenities == ["spa"]
    assert prop.images == ["http://example.com/x.jpg"]


# --------------------------------------------------------------------------- #
# _parse_rate_entry                                                           #
# --------------------------------------------------------------------------- #


def test_parse_rate_entry_flags_refundable_rate() -> None:
    rate = _parse_rate_entry(
        {
            "RoomTypeCode": "STD",
            "Name": "Standard",
            "TotalFare": "100.00",
            "Currency": "USD",
            "BookingCode": "bk-1",
            "IsRefundable": True,
            "CancellationPolicy": "Free cancel until 24h prior.",
        },
        fallback_currency=None,
    )
    assert rate is not None
    assert rate.is_refundable is True
    assert rate.cancellation_policy.default == "Free cancel until 24h prior."
    assert rate.rate_key == "bk-1"


def test_parse_rate_entry_non_refundable_has_no_cancellation_policy() -> None:
    rate = _parse_rate_entry(
        {
            "RoomTypeCode": "STD",
            "TotalFare": "150.00",
            "Currency": "USD",
            "BookingCode": "bk-2",
            # IsRefundable omitted — should default to False
        },
        fallback_currency=None,
    )
    assert rate is not None
    assert rate.is_refundable is False
    assert rate.cancellation_policy is None


def test_parse_rate_entry_missing_price_returns_none() -> None:
    assert _parse_rate_entry({"RoomTypeCode": "STD"}, fallback_currency="USD") is None


def test_parse_rate_entry_unparseable_price_returns_none() -> None:
    assert (
        _parse_rate_entry(
            {"RoomTypeCode": "STD", "TotalFare": "not a number"},
            fallback_currency="USD",
        )
        is None
    )


def test_parse_rate_entry_falls_back_on_currency_when_room_missing() -> None:
    rate = _parse_rate_entry(
        {"RoomTypeCode": "STD", "TotalFare": "99.00"},
        fallback_currency="AED",
    )
    assert rate is not None
    assert rate.price.currency == "AED"


def test_parse_rate_entry_defaults_max_occupancy_to_two() -> None:
    rate = _parse_rate_entry(
        {"RoomTypeCode": "STD", "TotalFare": "10.00", "Currency": "USD"},
        fallback_currency=None,
    )
    assert rate is not None
    assert rate.room.max_occupancy == 2


# --------------------------------------------------------------------------- #
# _parse_rate (PreBook)                                                       #
# --------------------------------------------------------------------------- #


def test_parse_rate_prebook_happy_path() -> None:
    payload = {
        "PreBookResult": {
            "Currency": "INR",
            "Rooms": [
                {
                    "RoomTypeCode": "DLX",
                    "Name": "Deluxe",
                    "TotalFare": "7500.00",
                    "Currency": "INR",
                    "BookingCode": "rk-xyz",
                }
            ],
        }
    }
    rate = _parse_rate(payload)
    assert rate.rate_key == "rk-xyz"
    assert rate.price.amount == Decimal("7500.00")


def test_parse_rate_non_dict_raises_validation_failed() -> None:
    with pytest.raises(ValidationFailedError):
        _parse_rate("not an object")


def test_parse_rate_empty_rooms_raises_validation_failed() -> None:
    with pytest.raises(ValidationFailedError):
        _parse_rate({"PreBookResult": {"Rooms": []}})


def test_parse_rate_unpricable_room_raises_validation_failed() -> None:
    with pytest.raises(ValidationFailedError):
        _parse_rate({"Rooms": [{"RoomTypeCode": "STD"}]})  # no TotalFare


def test_parse_rate_tolerates_flat_response_without_prebookresult_wrapper() -> None:
    payload = {
        "Rooms": [
            {
                "RoomTypeCode": "STD",
                "Name": "Std",
                "TotalFare": "999",
                "Currency": "USD",
                "BookingCode": "bk-xyz",
            }
        ]
    }
    rate = _parse_rate(payload)
    assert rate.rate_key == "bk-xyz"
    assert rate.price.currency == "USD"


# --------------------------------------------------------------------------- #
# _parse_board_basis                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Breakfast", BoardBasis.BB),
        ("BB", BoardBasis.BB),
        ("half board", BoardBasis.HB),
        ("HB", BoardBasis.HB),
        ("full board", BoardBasis.FB),
        ("All Inclusive", BoardBasis.AI),
        ("room only", BoardBasis.RO),
        ("unknown tag", BoardBasis.RO),
        ("", BoardBasis.RO),
        (None, BoardBasis.RO),
    ],
)
def test_parse_board_basis_handles_known_and_unknown(raw, expected) -> None:
    assert _parse_board_basis(raw) == expected
