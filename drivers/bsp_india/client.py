"""BSPlink client — scaffolded for v0.

Real BSPlink integration is two separate wire shapes:

* **SFTP** — the production route for HAF file drops. Needs
  ``paramiko`` / ``asyncssh`` plus tenant-provided key material. Not
  shipped in v0.
* **Web forms** — the interactive portal at
  ``https://www.bsplink.iata.org``. HTTP POST + HTML parsing, not a JSON
  API. Not shipped in v0.

In v0 the client supports two paths:

* **Local file fetch.** When ``config.file_source_dir`` is set, the
  client reads the most appropriate HAF file for the requested period.
  This is the path we expect most tenants to use until the full
  integration lands.
* **HTTP scaffold.** If no ``file_source_dir`` is configured the client
  raises :class:`PermanentError` with a clear message, rather than
  silently making an unauthenticated request.

ADM and ACM submission are both exposed on the client as scaffolded
async methods that always raise
:class:`CapabilityNotSupportedError`. The driver advertises the same
limitation via its manifest.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    NotFoundError,
    PermanentError,
)

from .config import BSPIndiaConfig
from .errors import DRIVER_NAME, map_bsp_error

logger = logging.getLogger(__name__)


class BSPIndiaClient:
    """Async client for BSPlink / HAF file acquisition.

    One instance per driver; safe for concurrent use. The HTTP client is
    lazily created and only used on the (scaffolded) network path so
    tests that exclusively use ``file_source_dir`` can run without
    httpx network stubs.
    """

    def __init__(
        self,
        config: BSPIndiaConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._http = http_client
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Release the httpx client if we created it."""
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> BSPIndiaClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ #
    # Public verbs                                                        #
    # ------------------------------------------------------------------ #

    async def fetch_statement(self, period_start: date, period_end: date) -> bytes:
        """Return the HAF file bytes for a settlement period.

        * If :attr:`BSPIndiaConfig.file_source_dir` is set, read the
          file whose name best matches the period (see
          :meth:`_resolve_local_file`).
        * Otherwise raise :class:`PermanentError` — direct BSPlink HTTP
          download requires a future enhancement.

        Raises:
            NotFoundError: no matching file in ``file_source_dir``.
            PermanentError: HTTP path is requested but not implemented.
            ValidationFailedError: file cannot be read.
        """
        if self._config.file_source_dir:
            return await asyncio.to_thread(
                self._read_local_file, period_start, period_end
            )
        return await self._fetch_via_http(period_start, period_end)

    async def submit_adm(self, payload: dict[str, Any]) -> str:
        """Not supported in v0.

        BSPlink ADM submission runs through a stateful web form
        workflow; automating it requires either the browser-runner stack
        we have not shipped yet or a tenant-side RPA integration. The
        driver manifest declares ``raise_adm`` as ``not_supported`` for
        the same reason.
        """
        del payload  # signature parity with the production client
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "BSP India ADM submission is not supported in v0. The BSPlink portal "
            "requires a form-driven web workflow that is scheduled for a later "
            "release.",
        )

    async def submit_acm(self, payload: dict[str, Any]) -> str:
        """Not supported in v0 (see :meth:`submit_adm`)."""
        del payload
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "BSP India ACM submission is not supported in v0 (see submit_adm).",
        )

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _read_local_file(self, period_start: date, period_end: date) -> bytes:
        """Read a HAF file from ``file_source_dir`` for the given period.

        File-name convention (v0):

            HAF_<AGENT_IATA>_<YYYYMMDD>_<YYYYMMDD>.txt

        The method first tries the exact name above; if not present it
        falls back to any file whose name contains both dates. A real
        integration will key off the BSPlink-assigned filename which
        differs across agents.
        """
        directory = Path(self._config.file_source_dir or "").expanduser()
        if not directory.is_dir():
            raise PermanentError(
                DRIVER_NAME,
                f"file_source_dir {directory!s} does not exist or is not a directory.",
            )
        exact_name = (
            f"HAF_{self._config.agent_iata_code}_"
            f"{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.txt"
        )
        candidate = directory / exact_name
        if candidate.is_file():
            return candidate.read_bytes()

        # Fallback: any file in the directory that contains both dates.
        start_tag = period_start.strftime("%Y%m%d")
        end_tag = period_end.strftime("%Y%m%d")
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            name = entry.name
            if start_tag in name and end_tag in name:
                return entry.read_bytes()

        raise NotFoundError(
            DRIVER_NAME,
            (
                f"No HAF file in {directory!s} matching period "
                f"{start_tag}..{end_tag}. Expected {exact_name} or a filename "
                f"containing both dates."
            ),
        )

    async def _fetch_via_http(self, period_start: date, period_end: date) -> bytes:
        """Scaffolded HTTP path — always fails cleanly in v0.

        The real implementation will:

        1. Authenticate against BSPlink (form login, cookie jar).
        2. Navigate the statement-download page for the given period.
        3. Stream the resulting HAF file back as bytes.

        None of those steps are implemented in v0; we raise a clean
        :class:`PermanentError` so the orchestrator can surface a
        helpful message to the user.
        """
        del period_start, period_end  # scaffold only
        raise map_bsp_error(
            501,
            b"direct BSPlink HTTP fetch not implemented",
            vendor_ref="bsplink http scaffold",
        )

    # Retained so the symbol exists even if a future refactor wires up a
    # cached httpx client — currently unused.
    def _ensure_http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._config.bsplink_base_url.rstrip("/"),
                timeout=self._config.timeout_seconds,
            )
        return self._http


# Avoid the unused-import warning for ``os`` if we drop the path helpers later.
_ = os


__all__ = ["BSPIndiaClient"]
