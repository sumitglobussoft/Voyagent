"""HTTP-layer tests for :class:`AmadeusClient` and :class:`TokenManager`.

Mocks httpx traffic with ``respx`` (matching the style of ``test_driver.py``)
so this file is idiomatic with the rest of the amadeus driver test suite.
Covers token caching, auth header shape, query-param serialisation, and
the 401-then-refresh dance in :meth:`AmadeusClient._request`.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import SecretStr

from drivers._contracts.errors import (
    AuthenticationError,
    PermanentError,
    UpstreamTimeoutError,
)
from drivers.amadeus.client import AmadeusClient
from drivers.amadeus.config import AmadeusConfig

pytestmark = pytest.mark.asyncio


def _config() -> AmadeusConfig:
    return AmadeusConfig(
        api_base="https://test.api.amadeus.example",
        client_id="cid",
        client_secret=SecretStr("csecret"),
        timeout_seconds=5.0,
        max_retries=2,
    )


def _token_body(expires_in: int = 1799) -> dict:
    return {
        "type": "amadeusOAuth2Token",
        "access_token": "tok-abc",
        "token_type": "Bearer",
        "expires_in": expires_in,
        "state": "approved",
    }


@respx.mock
async def test_get_json_attaches_bearer_token() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    search_route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AmadeusClient(_config())
    try:
        await client.get_json("/v2/shopping/flight-offers", params={"a": "b"})
    finally:
        await client.aclose()

    auth = search_route.calls.last.request.headers.get("authorization")
    assert auth == "Bearer tok-abc"


@respx.mock
async def test_get_json_serialises_query_params() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AmadeusClient(_config())
    try:
        await client.get_json(
            "/v2/shopping/flight-offers",
            params={"originLocationCode": "BOM", "max": 10},
        )
    finally:
        await client.aclose()

    sent = dict(route.calls.last.request.url.params)
    assert sent["originLocationCode"] == "BOM"
    assert sent["max"] == "10"


@respx.mock
async def test_post_json_sets_amadeus_content_type() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    route = respx.post(f"{base}/v1/booking/flight-orders").mock(
        return_value=httpx.Response(201, json={"data": {"id": "x"}})
    )

    client = AmadeusClient(_config())
    try:
        await client.post_json("/v1/booking/flight-orders", json={"data": {}})
    finally:
        await client.aclose()

    assert (
        route.calls.last.request.headers["content-type"]
        == "application/vnd.amadeus+json"
    )


@respx.mock
async def test_token_is_cached_across_calls() -> None:
    base = _config().api_base.rstrip("/")
    token_route = respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AmadeusClient(_config())
    try:
        await client.get_json("/v2/shopping/flight-offers")
        await client.get_json("/v2/shopping/flight-offers")
        await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()

    assert token_route.call_count == 1


@respx.mock
async def test_401_on_token_raises_authentication_error() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(
            401,
            json={"error": "invalid_client", "error_description": "bad creds"},
        )
    )

    client = AmadeusClient(_config())
    try:
        with pytest.raises(AuthenticationError):
            await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()


@respx.mock
async def test_401_on_data_call_triggers_token_refresh_once() -> None:
    base = _config().api_base.rstrip("/")
    token_route = respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    # First data call: 401 (stale token). Second: 200.
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        side_effect=[
            httpx.Response(401, json={"errors": [{"code": 38191, "title": "Invalid token"}]}),
            httpx.Response(200, json={"data": []}),
        ]
    )

    client = AmadeusClient(_config())
    try:
        body = await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()

    # Token fetched initially, cache invalidated by 401, fetched again.
    assert token_route.call_count == 2
    assert body == {"data": []}


@respx.mock
async def test_204_returns_none() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    respx.delete(f"{base}/v1/booking/flight-orders/xyz").mock(
        return_value=httpx.Response(204)
    )

    client = AmadeusClient(_config())
    try:
        result = await client.delete("/v1/booking/flight-orders/xyz")
    finally:
        await client.aclose()
    assert result is None


@respx.mock
async def test_non_json_2xx_body_raises_permanent_error() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, content=b"<html>edge-rewritten</html>")
    )

    client = AmadeusClient(_config())
    try:
        with pytest.raises(PermanentError):
            await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()


@respx.mock
async def test_timeout_retries_then_surfaces_upstream_timeout() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    route = respx.get(f"{base}/v2/shopping/flight-offers").mock(
        side_effect=httpx.ReadTimeout("slow")
    )

    cfg = _config()
    client = AmadeusClient(cfg)
    try:
        with pytest.raises(UpstreamTimeoutError):
            await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()

    # max_retries=2 + first attempt => 3 total attempts
    assert route.call_count == cfg.max_retries + 1


@respx.mock
async def test_token_response_missing_access_token_raises_permanent_error() -> None:
    base = _config().api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"state": "approved"})  # no access_token
    )

    client = AmadeusClient(_config())
    try:
        with pytest.raises(PermanentError):
            await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()


@respx.mock
async def test_token_form_body_carries_credentials() -> None:
    base = _config().api_base.rstrip("/")
    token_route = respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=_token_body())
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AmadeusClient(_config())
    try:
        await client.get_json("/v2/shopping/flight-offers")
    finally:
        await client.aclose()

    body = token_route.calls.last.request.content.decode("ascii")
    assert "grant_type=client_credentials" in body
    assert "client_id=cid" in body
    assert "client_secret=csecret" in body


async def test_aclose_closes_owned_http_client() -> None:
    client = AmadeusClient(_config())
    assert client._owns_client is True
    await client.aclose()
    assert client._http.is_closed is True


async def test_aclose_does_not_close_injected_http_client() -> None:
    """If the caller passed the httpx client in, they own its lifecycle."""
    http = httpx.AsyncClient(base_url="https://test.api.amadeus.example")
    client = AmadeusClient(_config(), http_client=http)
    await client.aclose()
    assert http.is_closed is False
    await http.aclose()
