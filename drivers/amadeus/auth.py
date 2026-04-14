"""OAuth2 client-credentials token management for Amadeus Self-Service.

Tokens are short-lived (typically ~1800s). :class:`TokenManager` fetches on
demand, caches in memory, and refreshes 60s before expiry. A single
:class:`asyncio.Lock` serializes refreshes so concurrent callers share one
network round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from .config import AmadeusConfig
from .errors import DRIVER_NAME, map_amadeus_error

logger = logging.getLogger(__name__)

_REFRESH_BUFFER_SECONDS = 60.0
_TOKEN_PATH = "/v1/security/oauth2/token"


@dataclass(slots=True)
class _CachedToken:
    access_token: str
    expires_at: float  # monotonic wall-clock from time.monotonic()


class TokenManager:
    """Fetches and caches bearer tokens for the Amadeus Self-Service API.

    Thread-safe enough for asyncio: a single lock gates refreshes. Does not
    share state across processes — each worker gets its own cache. If the
    token endpoint responds 401 the credentials are bad and we surface an
    :class:`AuthenticationError`.
    """

    def __init__(self, config: AmadeusConfig, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client
        self._lock = asyncio.Lock()
        self._cached: _CachedToken | None = None

    async def get_token(self) -> str:
        """Return a bearer token, refreshing if expired or near expiry."""
        now = time.monotonic()
        cached = self._cached
        if cached is not None and cached.expires_at - _REFRESH_BUFFER_SECONDS > now:
            return cached.access_token

        async with self._lock:
            # Another coroutine may have refreshed while we were waiting.
            now = time.monotonic()
            cached = self._cached
            if cached is not None and cached.expires_at - _REFRESH_BUFFER_SECONDS > now:
                return cached.access_token
            return await self._refresh_locked()

    async def invalidate(self) -> None:
        """Drop the cached token. Next call to :meth:`get_token` refetches."""
        async with self._lock:
            self._cached = None

    async def _refresh_locked(self) -> str:
        data = {
            "grant_type": "client_credentials",
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret.get_secret_value(),
        }
        try:
            response = await self._client.post(
                self._token_url(),
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise _timeout_error("Timed out fetching Amadeus OAuth2 token.") from exc
        except httpx.HTTPError as exc:
            from drivers._contracts.errors import TransientError

            raise TransientError(
                DRIVER_NAME,
                f"Network error fetching Amadeus token: {exc!s}",
            ) from exc

        if response.status_code >= 400:
            raise map_amadeus_error(response)

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not access_token or not isinstance(expires_in, (int, float)):
            from drivers._contracts.errors import PermanentError

            raise PermanentError(
                DRIVER_NAME,
                "Amadeus token response missing access_token / expires_in.",
                vendor_ref=str(payload)[:200],
            )

        self._cached = _CachedToken(
            access_token=str(access_token),
            expires_at=time.monotonic() + float(expires_in),
        )
        logger.debug("amadeus: refreshed bearer token; expires_in=%s", expires_in)
        return self._cached.access_token

    def _token_url(self) -> str:
        return f"{self._config.api_base.rstrip('/')}{_TOKEN_PATH}"


def _timeout_error(message: str):
    """Lazy import helper to avoid circulars."""
    from drivers._contracts.errors import UpstreamTimeoutError

    return UpstreamTimeoutError(DRIVER_NAME, message)


__all__ = ["TokenManager"]
