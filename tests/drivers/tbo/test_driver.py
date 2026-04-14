"""HTTP-mocked tests for the TBO driver.

Uses respx to intercept httpx traffic; tests never hit a real TBO
endpoint. Credentials default to obviously-fake values so a
misconfigured CI job can never accidentally call production.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import pytest_asyncio
import respx
from pydantic import SecretStr

from drivers._contracts.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    PermanentError,
)
from drivers._contracts.hotel_search import HotelSearchCriteria
from drivers.tbo.config import TBOConfig
from drivers.tbo.driver import TBODriver

pytestmark = pytest.mark.asyncio


_TEST_BASE = "https://api.tbotechnology.example/TBOHolidays_HotelAPI"


def _config() -> TBOConfig:
    return TBOConfig(
        api_base=_TEST_BASE,
        username="test-user",
        password=SecretStr("test-pass"),
        timeout_seconds=5.0,
        max_retries=0,
    )


def _criteria() -> HotelSearchCriteria:
    return HotelSearchCriteria(
        destination_country="IN",
        destination_city="DEL",
        check_in=date(2026, 5, 10),
        check_out=date(2026, 5, 12),
        guest_count=2,
    )


@pytest_asyncio.fixture
async def tbo_driver() -> TBODriver:
    driver = TBODriver(_config())
    try:
        yield driver
    finally:
        await driver.aclose()


def test_init_without_credentials_raises_permanent_error() -> None:
    empty = TBOConfig(
        api_base=_TEST_BASE,
        username="",
        password=SecretStr(""),
    )
    with pytest.raises(PermanentError, match="credentials missing"):
        TBODriver(empty)


def test_manifest_declares_partial_search_and_unsupported_book(
    tbo_driver: TBODriver,
) -> None:
    m = tbo_driver.manifest()
    assert m.driver == "tbo"
    assert set(m.implements) == {"HotelSearchDriver", "HotelBookingDriver"}
    assert m.capabilities["search"] == "partial"
    assert m.capabilities["check_rate"] == "partial"
    assert m.capabilities["book"] == "not_supported"
    assert m.capabilities["cancel"] == "not_supported"
    assert "rest" in m.transport
    assert "tenant_credentials" in m.requires


@respx.mock
async def test_search_happy_path_maps_into_hotel_offers(
    tbo_driver: TBODriver,
) -> None:
    respx.post(f"{_TEST_BASE}/Search").mock(
        return_value=httpx.Response(
            200,
            json={
                "Currency": "INR",
                "HotelSearchResult": {
                    "HotelResults": [
                        {
                            "HotelCode": "TBO-1001",
                            "HotelName": "Taj Palace",
                            "CityName": "DEL",
                            "CountryCode": "IN",
                            "Address": "Chanakyapuri",
                            "HotelRating": 5,
                            "Latitude": 28.59,
                            "Longitude": 77.17,
                            "HotelFacilities": ["pool", "spa"],
                            "Images": ["https://example.com/a.jpg"],
                            "Rooms": [
                                {
                                    "RoomTypeCode": "DLX",
                                    "Name": "Deluxe King",
                                    "BedType": "king",
                                    "MealType": "Breakfast",
                                    "MaxOccupancy": 2,
                                    "TotalFare": "12500.00",
                                    "Currency": "INR",
                                    "BookingCode": "rk-abc-123",
                                    "IsRefundable": True,
                                    "CancellationPolicy": "Free until 48h prior.",
                                }
                            ],
                        }
                    ]
                },
            },
        )
    )

    offers = await tbo_driver.search(_criteria())
    assert len(offers) == 1
    offer = offers[0]
    assert offer.property_name == "Taj Palace"
    assert offer.property_ref == "TBO-1001"
    assert offer.address_country == "IN"
    assert offer.cost.currency == "INR"
    assert str(offer.cost.amount) == "12500.00"
    assert offer.offer_ref == "rk-abc-123"


@respx.mock
async def test_search_results_exposes_canonical_shape(
    tbo_driver: TBODriver,
) -> None:
    respx.post(f"{_TEST_BASE}/Search").mock(
        return_value=httpx.Response(
            200,
            json={
                "Currency": "INR",
                "HotelSearchResult": {
                    "HotelResults": [
                        {
                            "HotelCode": "TBO-1001",
                            "HotelName": "Taj Palace",
                            "CityName": "DEL",
                            "CountryCode": "IN",
                            "HotelRating": 5,
                            "Rooms": [
                                {
                                    "RoomTypeCode": "DLX",
                                    "Name": "Deluxe King",
                                    "MealType": "Breakfast",
                                    "MaxOccupancy": 2,
                                    "TotalFare": "12500.00",
                                    "Currency": "INR",
                                    "BookingCode": "rk-abc-123",
                                }
                            ],
                        }
                    ]
                },
            },
        )
    )

    results = await tbo_driver.search_results(_criteria())
    assert len(results) == 1
    r = results[0]
    assert r.property.name == "Taj Palace"
    assert r.rates[0].rate_key == "rk-abc-123"
    assert r.check_in == date(2026, 5, 10)


@respx.mock
async def test_search_401_maps_to_authentication_error(
    tbo_driver: TBODriver,
) -> None:
    respx.post(f"{_TEST_BASE}/Search").mock(
        return_value=httpx.Response(
            401, json={"Error": "Invalid credentials"}
        )
    )
    with pytest.raises(AuthenticationError, match="credentials"):
        await tbo_driver.search(_criteria())


async def test_book_raises_capability_not_supported(tbo_driver: TBODriver) -> None:
    with pytest.raises(CapabilityNotSupportedError, match="needs real credentials"):
        await tbo_driver.book("rk-abc-123", None)  # type: ignore[arg-type]


async def test_cancel_raises_capability_not_supported(tbo_driver: TBODriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await tbo_driver.cancel("bk-1")


async def test_read_raises_capability_not_supported(tbo_driver: TBODriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await tbo_driver.read("bk-1")
