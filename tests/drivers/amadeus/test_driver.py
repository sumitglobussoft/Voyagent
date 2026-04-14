"""Integration-style tests for :class:`AmadeusDriver` using ``respx``."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import SecretStr

from drivers._contracts.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationFailedError,
)
from drivers._contracts.fare_search import FareSearchCriteria
from drivers.amadeus.driver import AmadeusDriver
from schemas.canonical import (
    Email,
    Gender,
    Passenger,
    PassengerType,
    Passport,
    Phone,
)

pytestmark = pytest.mark.asyncio


def _criteria(**overrides) -> FareSearchCriteria:
    base = dict(
        passengers={PassengerType.ADULT: 1},
        origin="BOM",
        destination="DXB",
        outbound_date=date(2026, 5, 10),
    )
    base.update(overrides)
    return FareSearchCriteria(**base)


def _make_passenger(
    *,
    passenger_id: str,
    tenant_id: str,
    with_passport: bool = True,
    with_dob: bool = True,
) -> Passenger:
    now = datetime(2026, 4, 14, 0, 0, tzinfo=timezone.utc)
    passport = None
    if with_passport:
        passport = Passport(
            number=SecretStr("Z1234567"),
            issuing_country="IN",
            given_name="JANE",
            family_name="DOE",
            date_of_birth=date(1990, 1, 15),
            gender=Gender.FEMALE,
            issue_date=date(2020, 1, 1),
            expiry_date=date(2030, 1, 1),
            place_of_birth="MUMBAI",
        )
    return Passenger(
        id=passenger_id,
        tenant_id=tenant_id,
        type=PassengerType.ADULT,
        given_name="Jane",
        family_name="Doe",
        date_of_birth=date(1990, 1, 15) if with_dob else None,
        gender=Gender.FEMALE,
        nationality="IN",
        passport=passport,
        phones=[Phone(e164="+919876543210", label="mobile")],
        emails=[Email(address="jane@example.com")],
        created_at=now,
        updated_at=now,
    )


def _build_resolver(passenger: Passenger):
    from voyagent_agent_runtime.passenger_resolver import (
        InMemoryPassengerResolver,
    )

    return InMemoryPassengerResolver({passenger.id: passenger})


# --------------------------------------------------------------------------- #
# manifest                                                                    #
# --------------------------------------------------------------------------- #


async def test_manifest_declares_expected_capabilities(amadeus_driver: AmadeusDriver) -> None:
    m = amadeus_driver.manifest()
    assert m.driver == "amadeus"
    assert m.version == AmadeusDriver.version
    assert set(m.implements) == {"FareSearchDriver", "PNRDriver"}
    assert m.capabilities["search"] == "full"
    assert m.capabilities["create"] == "full"
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


async def test_create_raises_permanent_error_when_cache_empty(
    amadeus_driver: AmadeusDriver,
    tenant_id: str,
) -> None:
    """Without a cached offer, ``create`` must fail fast with a clear hint."""
    from voyagent_agent_runtime.offer_cache import InMemoryOfferCache

    amadeus_driver._offer_cache = InMemoryOfferCache()
    passenger_id = "00000000-0000-7000-8000-000000000002"
    amadeus_driver._passenger_resolver = _build_resolver(
        _make_passenger(passenger_id=passenger_id, tenant_id=tenant_id)
    )
    with pytest.raises(PermanentError) as exc:
        await amadeus_driver.create(
            fare_ids=["00000000-0000-7000-8000-000000000001"],
            passenger_ids=[passenger_id],
        )
    assert "offer_expired_or_not_cached" in str(exc.value)


async def test_create_raises_permanent_error_when_no_cache_configured(
    amadeus_driver: AmadeusDriver,
    tenant_id: str,
) -> None:
    """A driver without an offer cache cannot book at all."""
    amadeus_driver._offer_cache = None
    amadeus_driver._passenger_resolver = _build_resolver(
        _make_passenger(
            passenger_id="00000000-0000-7000-8000-000000000002",
            tenant_id=tenant_id,
        )
    )
    with pytest.raises(PermanentError) as exc:
        await amadeus_driver.create(
            fare_ids=["00000000-0000-7000-8000-000000000001"],
            passenger_ids=["00000000-0000-7000-8000-000000000002"],
        )
    assert "offer cache" in str(exc.value).lower()


async def test_create_raises_when_no_passenger_resolver_configured(
    amadeus_driver: AmadeusDriver,
) -> None:
    """A driver without a resolver can't build real traveler blocks."""
    from voyagent_agent_runtime.offer_cache import InMemoryOfferCache

    amadeus_driver._offer_cache = InMemoryOfferCache()
    amadeus_driver._passenger_resolver = None
    with pytest.raises(PermanentError) as exc:
        await amadeus_driver.create(
            fare_ids=["00000000-0000-7000-8000-000000000001"],
            passenger_ids=["00000000-0000-7000-8000-000000000002"],
        )
    assert "passenger_resolver" in str(exc.value).lower()


@respx.mock
async def test_create_uses_cached_offer_and_posts_expected_body(
    amadeus_driver: AmadeusDriver,
    tenant_id: str,
    sample_token_response: dict,
    sample_order_response: dict,
) -> None:
    """Injected :class:`InMemoryOfferCache` + pre-seeded offer => POSTed booking."""
    from voyagent_agent_runtime.offer_cache import InMemoryOfferCache

    cache = InMemoryOfferCache()
    amadeus_driver._offer_cache = cache

    fare_id = "00000000-0000-7000-8000-0000000000aa"
    passenger_id = "00000000-0000-7000-8000-0000000000bb"
    amadeus_driver._passenger_resolver = _build_resolver(
        _make_passenger(passenger_id=passenger_id, tenant_id=tenant_id)
    )
    # Build a plausible cached offer. Deadline far in the future so we
    # skip the reprice path and land straight on /v1/booking/flight-orders.
    cached_offer = {
        "type": "flight-offer",
        "id": "42",
        "lastTicketingDateTime": "2099-01-01T00:00:00",
        "price": {"currency": "USD", "total": "345.60", "base": "300.00"},
        "travelerPricings": [
            {
                "travelerId": "1",
                "price": {"currency": "USD", "total": "345.60", "base": "300.00"},
            }
        ],
    }
    await cache.put(
        f"amadeus:fare:{fare_id}", cached_offer, ttl_seconds=600
    )

    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    booking_route = respx.post(f"{base}/v1/booking/flight-orders").mock(
        return_value=httpx.Response(201, json=sample_order_response)
    )

    pnr = await amadeus_driver.create(
        fare_ids=[fare_id],
        passenger_ids=[passenger_id],
    )

    assert booking_route.called
    import json as _json

    sent = _json.loads(booking_route.calls.last.request.content)
    assert sent["data"]["type"] == "flight-order"
    assert len(sent["data"]["flightOffers"]) == 1
    assert sent["data"]["flightOffers"][0]["id"] == "42"
    assert len(sent["data"]["travelers"]) == 1
    assert (
        sent["data"]["travelers"][0]["meta"]["voyagent_passenger_id"]
        == passenger_id
    )
    assert pnr.source == "amadeus"
    # Cache entry should be consumed so a retry surfaces a clear error.
    assert await cache.get(f"amadeus:fare:{fare_id}") is None


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


# --------------------------------------------------------------------------- #
# PassengerResolver integration                                               #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_create_uses_passenger_resolver_to_build_travelers(
    amadeus_driver: AmadeusDriver,
    tenant_id: str,
    sample_token_response: dict,
    sample_order_response: dict,
) -> None:
    """The Amadeus ``travelers`` block is built from canonical Passenger data."""
    from voyagent_agent_runtime.offer_cache import InMemoryOfferCache

    cache = InMemoryOfferCache()
    amadeus_driver._offer_cache = cache

    fare_id = "00000000-0000-7000-8000-0000000000cc"
    passenger_id = "00000000-0000-7000-8000-0000000000dd"
    passenger = _make_passenger(passenger_id=passenger_id, tenant_id=tenant_id)
    amadeus_driver._passenger_resolver = _build_resolver(passenger)

    cached_offer = {
        "type": "flight-offer",
        "id": "offer-99",
        "lastTicketingDateTime": "2099-01-01T00:00:00",
        "price": {"currency": "USD", "total": "345.60", "base": "300.00"},
        "travelerPricings": [
            {"travelerId": "1",
             "price": {"currency": "USD", "total": "345.60", "base": "300.00"}},
        ],
    }
    await cache.put(f"amadeus:fare:{fare_id}", cached_offer, ttl_seconds=600)

    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    booking_route = respx.post(f"{base}/v1/booking/flight-orders").mock(
        return_value=httpx.Response(201, json=sample_order_response)
    )

    await amadeus_driver.create(
        fare_ids=[fare_id],
        passenger_ids=[passenger_id],
    )

    import json as _json

    sent = _json.loads(booking_route.calls.last.request.content)
    travelers = sent["data"]["travelers"]
    assert len(travelers) == 1
    tr = travelers[0]
    assert tr["id"] == "1"
    assert tr["dateOfBirth"] == "1990-01-15"
    # Passport MRZ wins over passenger preferred name.
    assert tr["name"] == {"firstName": "JANE", "lastName": "DOE"}
    assert tr["gender"] == "FEMALE"
    assert tr["meta"]["voyagent_passenger_id"] == passenger_id
    # Passport document round-trips.
    docs = tr["documents"]
    assert len(docs) == 1
    assert docs[0]["documentType"] == "PASSPORT"
    assert docs[0]["number"] == "Z1234567"
    assert docs[0]["issuanceCountry"] == "IN"
    assert docs[0]["nationality"] == "IN"
    assert docs[0]["expiryDate"] == "2030-01-01"
    # Contact.
    assert tr["contact"]["emailAddress"] == "jane@example.com"
    assert tr["contact"]["phones"][0]["countryCallingCode"] == "91"
    assert tr["contact"]["phones"][0]["number"] == "9876543210"


async def test_create_raises_when_passenger_missing_dob(
    amadeus_driver: AmadeusDriver,
    tenant_id: str,
) -> None:
    """A passenger missing ``date_of_birth`` is a hard ValidationFailedError."""
    from voyagent_agent_runtime.offer_cache import InMemoryOfferCache

    cache = InMemoryOfferCache()
    amadeus_driver._offer_cache = cache

    fare_id = "00000000-0000-7000-8000-0000000000ee"
    passenger_id = "00000000-0000-7000-8000-0000000000ff"
    pax = _make_passenger(
        passenger_id=passenger_id,
        tenant_id=tenant_id,
        with_dob=False,
        with_passport=False,
    )
    amadeus_driver._passenger_resolver = _build_resolver(pax)

    cached_offer = {
        "id": "offer-1",
        "lastTicketingDateTime": "2099-01-01T00:00:00",
        "travelerPricings": [],
    }
    await cache.put(f"amadeus:fare:{fare_id}", cached_offer, ttl_seconds=600)

    with pytest.raises(ValidationFailedError) as exc:
        await amadeus_driver.create(
            fare_ids=[fare_id],
            passenger_ids=[passenger_id],
        )
    assert "date_of_birth" in str(exc.value)


# --------------------------------------------------------------------------- #
# search pagination                                                           #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_honors_max_results(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_search_response: dict,
) -> None:
    """``FareSearchCriteria.max_results`` propagates to the ``max`` query param."""
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    search_route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=sample_search_response)
    )

    fares = await amadeus_driver.search(_criteria(max_results=100))

    assert search_route.called
    sent_params = dict(search_route.calls.last.request.url.params)
    assert sent_params["max"] == "100"
    assert len(fares) <= 100


async def test_search_rejects_max_results_above_250(
    amadeus_driver: AmadeusDriver,
) -> None:
    """Validation in ``FareSearchCriteria`` rejects anything above 250."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _criteria(max_results=500)


@respx.mock
async def test_search_default_max_results_is_50(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
    sample_search_response: dict,
) -> None:
    """Existing callers that don't set ``max_results`` keep the old behaviour."""
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    search_route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=sample_search_response)
    )

    await amadeus_driver.search(_criteria())

    sent_params = dict(search_route.calls.last.request.url.params)
    assert sent_params["max"] == "50"
