"""Shared fixtures for the Amadeus driver test suite.

Uses ``respx`` to intercept httpx traffic; tests never hit a real
Amadeus endpoint. Credentials default to obviously-fake values so a
misconfigured CI job can never accidentally call production.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr

from drivers.amadeus.config import AmadeusConfig
from drivers.amadeus.driver import AmadeusDriver


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


@pytest.fixture
def tenant_id() -> str:
    return _uuid7_like()


@pytest.fixture
def amadeus_config() -> AmadeusConfig:
    """A safe config pinned to a non-routable test host.

    Never reads the ambient env — tests must be hermetic. Uses the
    sandbox-shaped base URL so any accidental un-mocked call goes to
    the dev environment, not production.
    """
    return AmadeusConfig(
        api_base="https://test.api.amadeus.example",  # .example TLD = RFC 2606
        client_id="test-client-id",
        client_secret=SecretStr("test-client-secret"),
        timeout_seconds=5.0,
        max_retries=2,
    )


@pytest_asyncio.fixture
async def amadeus_driver(
    amadeus_config: AmadeusConfig, tenant_id: str
) -> AmadeusDriver:
    driver = AmadeusDriver(amadeus_config, tenant_id=tenant_id)
    try:
        yield driver
    finally:
        await driver.aclose()


@pytest.fixture
def sample_token_response() -> dict[str, Any]:
    """Plausibly-shaped OAuth2 token response.

    Not a verbatim capture — based on the documented shape at
    developers.amadeus.com/self-service/apis-docs/guides/authorization.
    """
    return {
        "type": "amadeusOAuth2Token",
        "username": "test-client-id",
        "application_name": "Voyagent Test",
        "client_id": "test-client-id",
        "token_type": "Bearer",
        "access_token": "ey-test-access-token",
        "expires_in": 1799,
        "state": "approved",
        "scope": "",
    }


@pytest.fixture
def sample_search_response() -> dict[str, Any]:
    """Plausibly-shaped flight-offers response (one one-way offer for 1 ADT)."""
    return {
        "meta": {"count": 1},
        "data": [
            {
                "type": "flight-offer",
                "id": "1",
                "source": "GDS",
                "instantTicketingRequired": False,
                "nonHomogeneous": False,
                "oneWay": True,
                "lastTicketingDateTime": "2026-05-01T00:00:00",
                "numberOfBookableSeats": 9,
                "itineraries": [
                    {
                        "duration": "PT3H30M",
                        "segments": [
                            {
                                "departure": {
                                    "iataCode": "BOM",
                                    "terminal": "2",
                                    "at": "2026-05-10T09:00:00",
                                },
                                "arrival": {
                                    "iataCode": "DXB",
                                    "terminal": "3",
                                    "at": "2026-05-10T10:30:00",
                                },
                                "carrierCode": "EK",
                                "number": "507",
                                "aircraft": {"code": "77W"},
                                "operating": {"carrierCode": "EK"},
                                "duration": "PT3H30M",
                                "id": "1",
                                "numberOfStops": 0,
                                "blacklistedInEU": False,
                            }
                        ],
                    }
                ],
                "price": {
                    "currency": "USD",
                    "total": "345.60",
                    "base": "300.00",
                    "fees": [
                        {"amount": "0.00", "type": "SUPPLIER"},
                        {"amount": "0.00", "type": "TICKETING"},
                    ],
                    "grandTotal": "345.60",
                },
                "pricingOptions": {
                    "fareType": ["PUBLISHED"],
                    "includedCheckedBagsOnly": True,
                },
                "validatingAirlineCodes": ["EK"],
                "travelerPricings": [
                    {
                        "travelerId": "1",
                        "fareOption": "STANDARD",
                        "travelerType": "ADULT",
                        "price": {
                            "currency": "USD",
                            "total": "345.60",
                            "base": "300.00",
                            "taxes": [
                                {"amount": "30.00", "code": "YQ"},
                                {"amount": "15.60", "code": "IN"},
                            ],
                            "fees": [],
                        },
                        "fareDetailsBySegment": [
                            {
                                "segmentId": "1",
                                "cabin": "ECONOMY",
                                "fareBasis": "TLXOWIN",
                                "class": "T",
                                "includedCheckedBags": {"quantity": 1},
                            }
                        ],
                    }
                ],
            }
        ],
        "dictionaries": {
            "locations": {
                "BOM": {"cityCode": "BOM", "countryCode": "IN"},
                "DXB": {"cityCode": "DXB", "countryCode": "AE"},
            },
            "aircraft": {"77W": "BOEING 777-300ER"},
            "currencies": {"USD": "US DOLLAR"},
            "carriers": {"EK": "EMIRATES"},
        },
    }


@pytest.fixture
def sample_order_response() -> dict[str, Any]:
    """Plausibly-shaped flight-order resource (post-create / read)."""
    return {
        "data": {
            "type": "flight-order",
            "id": "eJzTd9cPCnYOdQkGAAqNAmw%3D",
            "queuingOfficeId": "NCE4D31SB",
            "associatedRecords": [
                {
                    "reference": "ABC123",
                    "creationDate": "2026-04-14T10:15:00",
                    "originSystemCode": "GDS",
                    "flightOfferId": "1",
                }
            ],
            "flightOffers": [
                {
                    "type": "flight-offer",
                    "id": "1",
                    "itineraries": [
                        {
                            "segments": [
                                {
                                    "departure": {"iataCode": "BOM", "at": "2026-05-10T09:00:00"},
                                    "arrival": {"iataCode": "DXB", "at": "2026-05-10T10:30:00"},
                                    "carrierCode": "EK",
                                    "number": "507",
                                    "aircraft": {"code": "77W"},
                                    "id": "1",
                                }
                            ]
                        }
                    ],
                    "price": {"currency": "USD", "total": "345.60", "base": "300.00"},
                    "travelerPricings": [],
                }
            ],
            "travelers": [
                {
                    "id": "1",
                    "dateOfBirth": "1990-01-15",
                    "name": {"firstName": "JANE", "lastName": "DOE"},
                    "gender": "FEMALE",
                    "contact": {"emailAddress": "jane@example.com"},
                }
            ],
            "ticketingAgreement": {
                "option": "CONFIRM",
                "dateTime": "2026-04-30T23:59:00",
            },
            "status": "CONFIRMED",
        }
    }
