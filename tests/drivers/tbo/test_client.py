"""Low-level tests for :class:`TBOClient`.

Exercises the HTTP layer directly (rather than through :class:`TBODriver`)
so auth header shape, timeout handling, and error mapping can be pinned
without the confound of driver-level parsing.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from pydantic import SecretStr

from drivers._contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    PermanentError,
    RateLimitError,
    TransientError,
    UpstreamTimeoutError,
    ValidationFailedError,
)
from drivers.tbo.client import TBOClient
from drivers.tbo.config import TBOConfig

pytestmark = pytest.mark.asyncio


_TEST_BASE = "https://api.tbotechnology.example/TBOHolidays_HotelAPI"


def _config() -> TBOConfig:
    return TBOConfig(
        api_base=_TEST_BASE,
        username="alice",
        password=SecretStr("s3cret"),
        timeout_seconds=2.0,
        max_retries=0,
    )


async def _client_with_transport(transport: httpx.MockTransport) -> TBOClient:
    http = httpx.AsyncClient(base_url=_TEST_BASE, transport=transport)
    return TBOClient(_config(), http_client=http)


async def test_post_json_attaches_basic_auth_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(200, json={"ok": True})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        await client.post_json("/Search", json={"foo": "bar"})
    finally:
        await client.aclose()

    expected = "Basic " + base64.b64encode(b"alice:s3cret").decode("ascii")
    assert captured["auth"] == expected
    assert "application/json" in captured["content_type"]


async def test_post_json_returns_decoded_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"HotelSearchResult": {"HotelResults": []}})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        body = await client.post_json("/Search", json={})
    finally:
        await client.aclose()

    assert body == {"HotelSearchResult": {"HotelResults": []}}


async def test_post_json_204_returns_none() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        body = await client.post_json("/Search", json={})
    finally:
        await client.aclose()

    assert body is None


async def test_post_json_401_maps_to_authentication_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"Error": "Invalid credentials"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(AuthenticationError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_403_maps_to_authorization_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"Error": "Account suspended"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(AuthorizationError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_400_maps_to_validation_failed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"Error": "CheckIn missing"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(ValidationFailedError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_429_maps_to_rate_limit_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"Error": "slow down"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(RateLimitError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_5xx_maps_to_transient_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"Error": "upstream down"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(TransientError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_4xx_other_maps_to_permanent_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"Error": "teapot"})

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(PermanentError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_timeout_maps_to_upstream_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=_request)

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(UpstreamTimeoutError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_network_error_maps_to_transient() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=_request)

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(TransientError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_post_json_error_body_non_json_still_raises_mapped_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"<html>gateway crashed</html>")

    client = await _client_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(TransientError):
            await client.post_json("/Search", json={})
    finally:
        await client.aclose()


async def test_client_is_reusable_for_owned_http() -> None:
    """A client that owns its httpx instance closes it on aclose()."""
    client = TBOClient(_config())
    # Private attr check is acceptable — this is a unit test of lifecycle.
    assert client._owns_client is True
    await client.aclose()
    assert client._http.is_closed is True
