"""Tally -> Voyagent error mapping.

Tally Gateway Server does not use HTTP status codes the way a REST service
would. Success and error bodies both commonly return HTTP 200 — the error
signal is the presence of a ``<LINEERROR>`` element, or plain-text junk
instead of XML, or specific textual markers like "company ... not open".

This module centralises that translation. Callers do::

    raise map_tally_error(status, body)
"""

from __future__ import annotations

import logging
import re
from typing import Final

from drivers._contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DriverError,
    PermanentError,
    TransientError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

DRIVER_NAME: Final[str] = "tally"

_PREVIEW_BYTES: Final[int] = 240

# Tally's "company not open" surfaces with slight variations across versions;
# match generously on the key phrase pair rather than an exact string.
_COMPANY_NOT_OPEN_RE: Final[re.Pattern[str]] = re.compile(
    r"company[^<>\n]{0,80}?not\s+open", re.IGNORECASE
)

_LINEERROR_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"<\s*LINEERROR\s*>(.*?)<\s*/\s*LINEERROR\s*>", re.IGNORECASE | re.DOTALL
)


def _preview(body: bytes | None) -> str:
    """Return a short, log-safe preview of a response body."""
    if not body:
        return ""
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return "<undecodable>"
    text = " ".join(text.split())
    if len(text) > _PREVIEW_BYTES:
        return text[:_PREVIEW_BYTES] + "..."
    return text


def _extract_line_error(body: bytes | None) -> str | None:
    """Return the inner text of the first ``<LINEERROR>`` element, if any."""
    if not body:
        return None
    match = _LINEERROR_RE.search(body)
    if not match:
        return None
    try:
        inner = match.group(1).decode("utf-8", errors="replace").strip()
    except Exception:  # pragma: no cover - defensive
        return None
    return inner or None


def _vendor_ref(http_status: int, body: bytes | None) -> str:
    preview = _preview(body)
    return f"HTTP {http_status} | {preview}" if preview else f"HTTP {http_status}"


def map_tally_error(
    http_status: int,
    xml_response: bytes | None,
    parse_error: Exception | None = None,
) -> DriverError:
    """Translate a Tally response or parse failure into a :class:`DriverError`.

    Precedence:
      1. ``parse_error`` set     -> :class:`ValidationFailedError`.
      2. HTTP 401 / 403          -> auth / authorization errors.
      3. HTTP 503 / 504          -> :class:`TransientError`.
      4. Other non-2xx           -> :class:`PermanentError`.
      5. HTTP 2xx with LINEERROR -> :class:`ConflictError` (company-not-open
         heuristic) or :class:`PermanentError`.
      6. HTTP 2xx non-XML body   -> :class:`PermanentError` with preview.
    """
    vendor_ref = _vendor_ref(http_status, xml_response)

    if parse_error is not None:
        return ValidationFailedError(
            DRIVER_NAME,
            f"Failed to parse Tally response: {parse_error!s}",
            vendor_ref=vendor_ref,
        )

    if http_status == 401:
        return AuthenticationError(
            DRIVER_NAME,
            "Tally gateway rejected basic-auth credentials.",
            vendor_ref=vendor_ref,
        )
    if http_status == 403:
        return AuthorizationError(
            DRIVER_NAME,
            "Tally gateway denied access to the requested company or report.",
            vendor_ref=vendor_ref,
        )
    if http_status in (503, 504):
        return TransientError(
            DRIVER_NAME,
            f"Tally gateway temporarily unavailable (HTTP {http_status}).",
            vendor_ref=vendor_ref,
        )
    if http_status >= 400:
        return PermanentError(
            DRIVER_NAME,
            f"Tally gateway returned HTTP {http_status}.",
            vendor_ref=vendor_ref,
        )

    # HTTP 2xx — examine the body for embedded error signals.
    line_error = _extract_line_error(xml_response)
    if line_error is not None:
        if _COMPANY_NOT_OPEN_RE.search(line_error):
            return ConflictError(
                DRIVER_NAME,
                (
                    "Tally reports the configured company is not open. "
                    "Open the company in Tally Prime on the desktop host and retry."
                ),
                vendor_ref=vendor_ref,
            )
        return PermanentError(
            DRIVER_NAME,
            f"Tally error: {line_error}",
            vendor_ref=vendor_ref,
        )

    # Plain-text non-XML bodies sometimes carry out-of-band errors.
    if xml_response is not None and xml_response.strip() and not xml_response.lstrip().startswith(b"<"):
        preview = _preview(xml_response)
        if _COMPANY_NOT_OPEN_RE.search(preview):
            return ConflictError(
                DRIVER_NAME,
                "Tally reports the configured company is not open.",
                vendor_ref=vendor_ref,
            )
        return PermanentError(
            DRIVER_NAME,
            f"Tally returned a non-XML body: {preview}",
            vendor_ref=vendor_ref,
        )

    # Nothing obviously wrong — callers should not reach here; return a
    # permanent error to be safe rather than silently succeeding.
    return PermanentError(
        DRIVER_NAME,
        "Unrecognised Tally response shape.",
        vendor_ref=vendor_ref,
    )


__all__ = ["DRIVER_NAME", "map_tally_error"]
