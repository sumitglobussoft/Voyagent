"""TBO-local error helpers."""

from __future__ import annotations

import httpx

from drivers._contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    DriverError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationFailedError,
)

DRIVER_NAME = "tbo"


def map_tbo_error(response: httpx.Response) -> DriverError:
    """Map a non-2xx TBO response into a canonical :class:`DriverError`.

    TBO error bodies vary across endpoints; we fall back to the raw text
    when the JSON shape is unfamiliar so operators can debug from logs.
    """
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    detail = ""
    if isinstance(body, dict):
        detail = str(
            body.get("Error")
            or body.get("message")
            or body.get("errorMessage")
            or body
        )
    else:
        detail = str(body)

    if status == 401:
        return AuthenticationError(DRIVER_NAME, f"TBO rejected credentials: {detail}")
    if status == 403:
        return AuthorizationError(DRIVER_NAME, f"TBO forbade operation: {detail}")
    if status == 429:
        return RateLimitError(DRIVER_NAME, f"TBO rate-limited: {detail}")
    if status in (400, 422):
        return ValidationFailedError(DRIVER_NAME, f"TBO validation failed: {detail}")
    if 500 <= status < 600:
        return TransientError(DRIVER_NAME, f"TBO upstream {status}: {detail}")
    return PermanentError(DRIVER_NAME, f"TBO error {status}: {detail}")


__all__ = ["DRIVER_NAME", "map_tbo_error"]
