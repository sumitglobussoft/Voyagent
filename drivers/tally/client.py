"""Thin HTTP client wrapping :class:`httpx.AsyncClient` for Tally Gateway.

Responsibilities:
  * POST XML envelopes to the Tally gateway,
  * apply exponential backoff with jitter on transient errors,
  * translate :class:`httpx` timeouts into :class:`UpstreamTimeoutError`,
  * surface non-2xx responses through :func:`map_tally_error`.

Body-level errors (HTTP 200 with ``<LINEERROR>``) are the driver layer's
concern, not the client's — this client returns raw bytes for the parser.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from drivers._contracts.errors import TransientError, UpstreamTimeoutError

from .config import TallyConfig
from .errors import DRIVER_NAME, map_tally_error

logger = logging.getLogger(__name__)

_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 10.0


class TallyClient:
    """Request executor for the Tally Gateway Server.

    One instance per driver; safe for concurrent use. Envelopes are built
    elsewhere (:mod:`drivers.tally.xml_builder`) and posted here as raw
    ``bytes``. The gateway expects the XML declaration at the top.
    """

    def __init__(
        self,
        config: TallyConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        auth = self._build_auth(config)
        self._http = http_client or httpx.AsyncClient(
            base_url=config.gateway_url.rstrip("/"),
            timeout=config.timeout_seconds,
            auth=auth,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client if we created it."""
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> TallyClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ #
    # Public verbs                                                       #
    # ------------------------------------------------------------------ #

    async def post_envelope(self, xml_bytes: bytes) -> bytes:
        """POST ``xml_bytes`` to the gateway and return the response body.

        Non-2xx responses are translated to :class:`DriverError` subclasses
        via :func:`map_tally_error`. Body-level error signals
        (``<LINEERROR>``) are NOT inspected here — callers running through
        :mod:`xml_parser` surface them.
        """
        return await self._post_with_retries(xml_bytes)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_auth(config: TallyConfig) -> tuple[str, str] | None:
        if config.basic_auth_user and config.basic_auth_password is not None:
            return (
                config.basic_auth_user,
                config.basic_auth_password.get_secret_value(),
            )
        return None

    async def _post_with_retries(self, xml_bytes: bytes) -> bytes:
        attempts = 0
        headers = {
            "Content-Type": "application/xml",
            "Accept": "application/xml",
        }
        while True:
            attempts += 1
            try:
                response = await self._http.post(
                    "/",
                    content=xml_bytes,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if self._should_retry(attempts):
                    await self._sleep_backoff(attempts)
                    continue
                raise UpstreamTimeoutError(
                    DRIVER_NAME,
                    f"Timeout posting envelope after {self._config.timeout_seconds}s.",
                ) from exc
            except httpx.HTTPError as exc:
                if self._should_retry(attempts):
                    await self._sleep_backoff(attempts)
                    continue
                raise TransientError(
                    DRIVER_NAME,
                    f"Network error posting to Tally gateway: {exc!s}",
                ) from exc

            if response.status_code < 400:
                return response.content or b""

            error = map_tally_error(response.status_code, response.content)
            if isinstance(error, TransientError) and self._should_retry(attempts):
                await self._sleep_backoff(attempts)
                continue
            raise error

    def _should_retry(self, attempts: int) -> bool:
        return attempts <= self._config.max_retries

    async def _sleep_backoff(self, attempts: int, *, retry_after: float | None = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, _MAX_BACKOFF_SECONDS)
        else:
            delay = min(_BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), _MAX_BACKOFF_SECONDS)
            delay = random.uniform(0, delay)
        logger.debug("tally: backing off %.2fs before retry #%s", delay, attempts)
        await asyncio.sleep(delay)


__all__ = ["TallyClient"]
