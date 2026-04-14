"""BSP India -> Voyagent error mapping.

BSPlink speaks two wire formats:

* Web forms on ``https://www.bsplink.iata.org`` — HTML/HTTP, non-REST.
* SFTP drops of HAF fixed-position text files.

Both eventually bubble up as standard ``DriverError`` subclasses through
:func:`map_bsp_error`. For v0 most call sites use the file-local path,
where HTTP status codes are synthetic (we simulate them for consistent
mapping). The ``parse_error`` path is what the HAF parser triggers on a
malformed record.
"""

from __future__ import annotations

import logging
from typing import Final

from drivers._contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    DriverError,
    NotFoundError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

DRIVER_NAME: Final[str] = "bsp_india"

_PREVIEW_BYTES: Final[int] = 240


def _preview(body: bytes | str | None) -> str:
    """Return a short, log-safe preview of a response body."""
    if not body:
        return ""
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            return "<undecodable>"
    else:
        text = body
    text = " ".join(text.split())
    if len(text) > _PREVIEW_BYTES:
        return text[:_PREVIEW_BYTES] + "..."
    return text


def map_bsp_error(
    http_status: int,
    body: bytes | str | None = None,
    *,
    parse_error: Exception | None = None,
    vendor_ref: str | None = None,
) -> DriverError:
    """Translate a BSPlink response or parse failure into a :class:`DriverError`.

    Precedence mirrors the other drivers' mappers:

      1. ``parse_error`` set  -> :class:`ValidationFailedError`.
      2. HTTP 401             -> :class:`AuthenticationError`.
      3. HTTP 403             -> :class:`AuthorizationError`.
      4. HTTP 404             -> :class:`NotFoundError`.
      5. HTTP 429             -> :class:`RateLimitError`.
      6. HTTP 5xx             -> :class:`TransientError` (503/504) or
                                  :class:`PermanentError` otherwise.
      7. Fallback             -> :class:`PermanentError`.
    """
    preview = _preview(body)
    ref = vendor_ref or (f"HTTP {http_status} | {preview}" if preview else f"HTTP {http_status}")

    if parse_error is not None:
        return ValidationFailedError(
            DRIVER_NAME,
            f"Failed to parse BSP India response: {parse_error!s}",
            vendor_ref=ref,
        )

    if http_status == 401:
        return AuthenticationError(
            DRIVER_NAME,
            "BSPlink rejected credentials.",
            vendor_ref=ref,
        )
    if http_status == 403:
        return AuthorizationError(
            DRIVER_NAME,
            "BSPlink denied access to the requested resource.",
            vendor_ref=ref,
        )
    if http_status == 404:
        return NotFoundError(
            DRIVER_NAME,
            "BSPlink resource not found (statement may not yet be published).",
            vendor_ref=ref,
        )
    if http_status == 429:
        return RateLimitError(
            DRIVER_NAME,
            "BSPlink rate-limit hit.",
            vendor_ref=ref,
        )
    if http_status in (503, 504):
        return TransientError(
            DRIVER_NAME,
            f"BSPlink temporarily unavailable (HTTP {http_status}).",
            vendor_ref=ref,
        )
    if 500 <= http_status < 600:
        return PermanentError(
            DRIVER_NAME,
            f"BSPlink upstream error (HTTP {http_status}).",
            vendor_ref=ref,
        )
    if http_status >= 400:
        return PermanentError(
            DRIVER_NAME,
            f"BSPlink returned HTTP {http_status}.",
            vendor_ref=ref,
        )

    return PermanentError(
        DRIVER_NAME,
        "Unrecognised BSPlink response shape.",
        vendor_ref=ref,
    )


__all__ = ["DRIVER_NAME", "map_bsp_error"]
