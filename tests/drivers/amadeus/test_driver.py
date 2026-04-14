"""Integration-style tests for :class:`AmadeusDriver` using ``respx``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from drivers._contracts.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    PermanentError,
    RateLimitError,
    TransientError,
)
from drivers._contracts.fare_search import FareSearchCriteria
from drivers.amadeus.driver import AmadeusDriver
from schemas.canonical import PassengerType

pytestmark = pytest.mark.asyncio


def _criteria() -> FareSearchCriteria:
    return FareSearchCriteria(
        passengers={PassengerType.ADULT: 1},
        origin="BOM",
        destination="DXB",
        outbound_date=date(2026, 5, 10),
    )


# --------------------------------------------------------------------------- #
# manifest                                                                    #
# --------------------------------------------------------------------------- #


async def test_manifest_declares_expected_capabilities(amadeus_driver: AmadeusDriver) -> None:
    m = amadeus_driver.manifest()
    assert m.driver == "amadeus"
    assert m.version == AmadeusDriver.version
    assert set(m.implements) == {"FareSearchDriver", "PNRDriver"}
    assert m.capabilities["search"] == "full"
    assert m.capabilities["create"] == "requires_offer_cache"
    assert m.capabilities["read"] == "full"
    assert m.capabilities["cancel"] == "full"
    assert m.capabilities["queue_read"] == "not_supported"
    assert m.capabilities["issue_ticket"] == "not_supported"
    assert m.capabilities["void_ticket"] == "not_supported"
    assert "rest" in m.transport
    assert "tenant_credentials" in m.requires


# --------------------------------------------------------------------------- #
# not-supported capabilities                                                  #
# --------------------------------------------------------------------------- #


async def test_queue_read_raises_not_supported(amadeus_driver: AmadeusDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await amadeus_driver.queue_read(7)


async def test_issue_ticket_raises_not_supported(amadeus_driver: AmadeusDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError) as exc:
        await amadeus_driver.issue_ticket("00000000-0000-7000-8000-000000000001")
    assert "Enterprise" in str(exc.value) or "enterprise" in str(exc.value).lower()


async def test_void_ticket_raises_not_supported(amadeus_driver: AmadeusDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await amadeus_driver.void_ticket("00000000-0000-7000-8000-000000000001")


async def test_create_raises_permanent_error_in_v0(amadeus_driver: AmadeusDriver) -> None:
    with pytest.raises(PermanentError) as exc:
        await amadeus_driver.create(
            fare_ids=["00000000-0000-7000-8000-000000000001"],
            passenger_ids=["00000000-0000-7000-8000-000000000002"],
        )
    assert "offer" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# auth + search happy path                                                    #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_happy_path_fetches_token_then_offers(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_search_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    token_route = respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    search_route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=sample_search_response)
    )

    fares = await amadeus_driver.search(_criteria())

    assert token_route.called
    assert search_route.called
    assert len(fares) == 1
    assert fares[0].total.currency == "USD"
    assert fares[0].total.amount == Decimal("345.60")
    assert fares[0].source == "amadeus"


@respx.mock
async def test_token_is_cached_across_calls(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_search_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    token_route = respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=sample_search_response)
    )

    await amadeus_driver.search(_criteria())
    await amadeus_driver.search(_criteria())

    assert token_route.call_count == 1


@respx.mock
async def test_token_401_raises_authentication_error(amadeus_driver: AmadeusDriver) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(
            401,
            json={"error": "invalid_client", "error_description": "Client credentials are invalid"},
        )
    )

    with pytest.raises(AuthenticationError):
        await amadeus_driver.search(_criteria())


# --------------------------------------------------------------------------- #
# retriable error classes                                                     #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_429_maps_to_rate_limit_with_retry_after(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    # All attempts 429 so retries are exhausted and the error surfaces.
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(
            429,
            headers={"Retry-After": "3"},
            json={"errors": [{"code": 38194, "title": "Too many requests"}]},
        )
    )

    with pytest.raises(RateLimitError) as exc:
        await amadeus_driver.search(_criteria())
    assert exc.value.retry_after_seconds == 3.0


@respx.mock
async def test_search_503_maps_to_transient(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(
            503, json={"errors": [{"code": 38189, "title": "Service unavailable"}]}
        )
    )

    with pytest.raises(TransientError):
        await amadeus_driver.search(_criteria())


# --------------------------------------------------------------------------- #
# read + cancel                                                               #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_read_maps_order_to_pnr(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_order_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    order_id = sample_order_response["data"]["id"]

    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v1/booking/flight-orders/{order_id}").mock(
        return_value=httpx.Response(200, json=sample_order_response)
    )

    pnr = await amadeus_driver.read(order_id)
    assert pnr.locator == "ABC123"
    assert pnr.source == "amadeus"
    assert pnr.source_ref == order_id


@respx.mock
async def test_cancel_calls_delete_then_read(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_order_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    order_id = sample_order_response["data"]["id"]

    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    delete_route = respx.delete(f"{base}/v1/booking/flight-orders/{order_id}").mock(
        return_value=httpx.Response(204)
    )
    # After cancel we round-trip through read(); the sample is still CONFIRMED
    # but any valid PNR is acceptable for this test.
    respx.get(f"{base}/v1/booking/flight-orders/{order_id}").mock(
        return_value=httpx.Response(200, json=sample_order_response)
    )

    pnr = await amadeus_driver.cancel(order_id)
    assert delete_route.called
    assert pnr.source == "amadeus"
