"""HTTP client for the TBO Hotels API.

Thin wrapper around :class:`httpx.AsyncClient`. TBO's Hotels endpoints
authenticate with HTTP Basic (username + password) on every POST, so
there is no separate token manager — we just attach the auth tuple to
each request.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from drivers._contracts.errors import TransientError, UpstreamTimeoutError

from .config import TBOConfig
from .errors import DRIVER_NAME, map_tbo_error

logger = logging.getLogger(__name__)


class TBOClient:
    """One-per-driver HTTP executor. Safe for concurrent use."""

    def __init__(
        self,
        config: TBOConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=config.api_base.rstrip("/"),
            timeout=config.timeout_seconds,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> TBOClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def post_json(self, path: str, *, json: Any) -> Any:
        """POST to ``path`` with Basic auth and return the decoded JSON body."""
        auth = (
            self._config.username,
            self._config.password.get_secret_value(),
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = await self._http.post(
                path,
                json=json,
                headers=headers,
                auth=auth,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError(
                DRIVER_NAME,
                f"Timeout on POST {path} after {self._config.timeout_seconds}s.",
            ) from exc
        except httpx.HTTPError as exc:
            raise TransientError(
                DRIVER_NAME, f"Network error on POST {path}: {exc!s}"
            ) from exc

        if response.status_code < 400:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        raise map_tbo_error(response)


__all__ = ["TBOClient"]
