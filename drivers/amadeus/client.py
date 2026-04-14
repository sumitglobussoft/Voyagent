"""Thin HTTP client wrapping :class:`httpx.AsyncClient` for Amadeus Self-Service.

Responsibilities:
  * inject the bearer token from :class:`TokenManager`,
  * apply exponential backoff with jitter on retriable errors,
  * honour ``Retry-After`` on 429 responses,
  * translate :class:`httpx` timeouts into :class:`UpstreamTimeoutError`,
  * re-raise all other non-2xx responses through :func:`map_amadeus_error`.

Mapping JSON payloads to canonical types is **not** done here; the client
returns the decoded JSON body and delegates to :mod:`mapping`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from drivers._contracts.errors import (
    AuthenticationError,
    PermanentError,
    RateLimitError,
    TransientError,
    UpstreamTimeoutError,
)

from .auth import TokenManager
from .config import AmadeusConfig
from .errors import DRIVER_NAME, map_amadeus_error

logger = logging.getLogger(__name__)

_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 10.0


class AmadeusClient:
    """Request executor. One instance per driver; safe for concurrent use."""

    def __init__(
        self,
        config: AmadeusConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=config.api_base.rstrip("/"),
            timeout=config.timeout_seconds,
        )
        self._tokens = TokenManager(config, self._http)

    async def aclose(self) -> None:
        """Close the underlying HTTP client if we created it."""
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> AmadeusClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ #
    # Public verbs                                                       #
    # ------------------------------------------------------------------ #

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post_json(self, path: str, *, json: Any) -> Any:
        return await self._request("POST", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        attempts = 0
        last_error: Exception | None = None
        while True:
            attempts += 1
            token = await self._tokens.get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.amadeus+json, application/json",
            }
            if json is not None:
                headers["Content-Type"] = "application/vnd.amadeus+json"

            try:
                response = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                last_error = UpstreamTimeoutError(
                    DRIVER_NAME,
                    f"Timeout on {method} {path} after {self._config.timeout_seconds}s.",
                )
                if self._should_retry(attempts):
                    await self._sleep_backoff(attempts)
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = TransientError(
                    DRIVER_NAME,
                    f"Network error on {method} {path}: {exc!s}",
                )
                if self._should_retry(attempts):
                    await self._sleep_backoff(attempts)
                    continue
                raise last_error from exc

            if response.status_code < 400:
                if response.status_code == 204 or not response.content:
                    return None
                return _decode_json_or_raise(response, method, path)

            error = map_amadeus_error(response)

            # 401 on a data call: token might have been revoked mid-session.
            # Invalidate cache and retry once.
            if isinstance(error, AuthenticationError) and attempts == 1:
                await self._tokens.invalidate()
                continue

            if isinstance(error, (TransientError, RateLimitError)) and self._should_retry(attempts):
                await self._sleep_backoff(attempts, retry_after=error.retry_after_seconds)
                last_error = error
                continue

            raise error

    def _should_retry(self, attempts: int) -> bool:
        return attempts <= self._config.max_retries

    async def _sleep_backoff(self, attempts: int, *, retry_after: float | None = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, _MAX_BACKOFF_SECONDS)
        else:
            delay = min(_BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), _MAX_BACKOFF_SECONDS)
            # Full jitter
            delay = random.uniform(0, delay)
        logger.debug("amadeus: backing off %.2fs before retry #%s", delay, attempts)
        await asyncio.sleep(delay)


def _decode_json_or_raise(
    response: httpx.Response,
    method: str,
    path: str,
) -> Any:
    """Decode a response body as JSON or raise a mapped :class:`DriverError`.

    Amadeus is contracted to send JSON for all 2xx data responses; a
    non-JSON body means the edge rewrote the response (captive portal,
    HTML error page, truncated stream). We treat that as a server
    protocol violation: a :class:`PermanentError` with the status code
    and a body preview so debugging isn't a nightmare.

    The same helper is used for non-2xx bodies whose JSON payload fails
    to decode, so "server sent garbage" always surfaces through one
    mapped error class, never as a raw :class:`json.JSONDecodeError`.
    """
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        preview = (response.text or "")[:200]
        raise PermanentError(
            DRIVER_NAME,
            (
                f"Amadeus returned non-JSON body on {method} {path} "
                f"(HTTP {response.status_code}): {preview!r}"
            ),
            vendor_ref=f"HTTP {response.status_code} non-json",
        ) from exc


__all__ = ["AmadeusClient"]
