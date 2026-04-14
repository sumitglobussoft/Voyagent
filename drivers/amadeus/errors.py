"""Amadeus -> Voyagent error mapping.

Amadeus returns errors with the shape::

    {"errors": [{"code": 38189, "title": "Internal error", "detail": "..."}]}

This module inspects an :class:`httpx.Response` and returns the appropriate
:class:`DriverError` subclass from :mod:`drivers._contracts.errors`.
"""

from __future__ import annotations

from typing import Any

import httpx

from drivers._contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DriverError,
    NotFoundError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationFailedError,
)

DRIVER_NAME = "amadeus"


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Best-effort parse of the ``Retry-After`` header in seconds."""
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extract_error_fields(response: httpx.Response) -> tuple[str | None, str, str]:
    """Return ``(code, title, detail)`` from an Amadeus error body, tolerant to shape drift."""
    body: Any
    try:
        body = response.json()
    except Exception:  # pragma: no cover - defensive
        return None, f"HTTP {response.status_code}", response.text[:500]

    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        code = first.get("code")
        title = first.get("title") or f"HTTP {response.status_code}"
        detail = first.get("detail") or first.get("description") or ""
        return (str(code) if code is not None else None), str(title), str(detail)

    # Some Amadeus endpoints return OAuth2 RFC-6749 shaped errors at /security/oauth2/token
    if isinstance(body, dict) and "error" in body:
        return (
            str(body.get("error")),
            str(body.get("error") or f"HTTP {response.status_code}"),
            str(body.get("error_description") or ""),
        )

    return None, f"HTTP {response.status_code}", str(body)[:500]


def _is_validation_code(code: str | None, title: str) -> bool:
    """Heuristic: does this 400 look like vendor-side validation (bad input)?"""
    if code and code.isdigit():
        # Amadeus validation codes are in the 4000 / 477 / 572 / 38xxx families.
        # Rather than hard-coding their catalog, we treat any 400 with a numeric
        # code as validation unless overridden by title keywords.
        return True
    lowered = title.lower()
    return any(
        kw in lowered
        for kw in ("invalid", "mandatory", "missing", "format", "parameter", "validation")
    )


def map_amadeus_error(response: httpx.Response) -> DriverError:
    """Translate an Amadeus non-2xx response into a :class:`DriverError`.

    Never raises — callers do ``raise map_amadeus_error(response)``. The
    driver identifier is fixed to ``"amadeus"``; the vendor's native error
    code and title are stitched into ``vendor_ref`` for traceability.
    """
    status = response.status_code
    code, title, detail = _extract_error_fields(response)
    vendor_ref = f"{code} {title}".strip() if code else title
    message = detail or title

    if status == 401:
        return AuthenticationError(DRIVER_NAME, message, vendor_ref=vendor_ref)
    if status == 403:
        return AuthorizationError(DRIVER_NAME, message, vendor_ref=vendor_ref)
    if status == 404:
        return NotFoundError(DRIVER_NAME, message, vendor_ref=vendor_ref)
    if status == 409:
        return ConflictError(DRIVER_NAME, message, vendor_ref=vendor_ref)
    if status == 429:
        return RateLimitError(
            DRIVER_NAME,
            message or "Rate limited by Amadeus.",
            vendor_ref=vendor_ref,
            retry_after_seconds=_parse_retry_after(response),
        )
    if status == 400:
        if _is_validation_code(code, title):
            return ValidationFailedError(DRIVER_NAME, message, vendor_ref=vendor_ref)
        return PermanentError(DRIVER_NAME, message, vendor_ref=vendor_ref)
    if status in (503, 504):
        return TransientError(
            DRIVER_NAME,
            message or f"Upstream {status} from Amadeus.",
            vendor_ref=vendor_ref,
            retry_after_seconds=_parse_retry_after(response),
        )
    if 500 <= status < 600:
        return PermanentError(
            DRIVER_NAME,
            message or f"Upstream {status} from Amadeus.",
            vendor_ref=vendor_ref,
        )

    return PermanentError(
        DRIVER_NAME,
        message or f"Unexpected status {status} from Amadeus.",
        vendor_ref=vendor_ref,
    )


__all__ = ["DRIVER_NAME", "map_amadeus_error"]
