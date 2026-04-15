"""Sentry + request instrumentation helpers.

This module is a *silent no-op* when ``VOYAGENT_SENTRY_DSN_API`` is unset,
which keeps local dev and CI free of Sentry noise. Nothing here should
raise at import time or at ``init_sentry()`` call time — the hosting
FastAPI app must come up even if observability is totally unconfigured.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Iterable, Mapping

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# PII scrubbing                                                               #
# --------------------------------------------------------------------------- #

_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-voyagent-auth-detail",
    "proxy-authorization",
}

_SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|refresh[_-]?token|access[_-]?token|authorization)",
    re.IGNORECASE,
)

# A JWT is three base64url segments separated by dots. We scrub anything
# that *looks* like one so accidental logging of a whole token string in
# an unrelated field is still caught.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+")

_REDACTED = "[scrubbed]"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _JWT_RE.sub(_REDACTED, value)
    if isinstance(value, Mapping):
        return {k: _scrub_mapping_entry(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub_value(v) for v in value]
        return type(value)(scrubbed) if isinstance(value, tuple) else scrubbed
    return value


def _scrub_mapping_entry(key: Any, value: Any) -> Any:
    if isinstance(key, str):
        if key.lower() in _SENSITIVE_HEADER_NAMES:
            return _REDACTED
        if _SENSITIVE_FIELD_PATTERNS.search(key):
            return _REDACTED
    return _scrub_value(value)


def _scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    req = event.get("request")
    if isinstance(req, dict):
        headers = req.get("headers")
        if isinstance(headers, dict):
            req["headers"] = {
                k: (_REDACTED if k.lower() in _SENSITIVE_HEADER_NAMES else _scrub_value(v))
                for k, v in headers.items()
            }
        cookies = req.get("cookies")
        if isinstance(cookies, dict):
            req["cookies"] = {k: _REDACTED for k in cookies}
        data = req.get("data")
        if isinstance(data, (dict, list)):
            req["data"] = _scrub_value(data)
        query = req.get("query_string")
        if isinstance(query, str):
            req["query_string"] = _JWT_RE.sub(_REDACTED, query)

    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = _scrub_value(extra)

    return event


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    try:
        return _scrub_event(event)
    except Exception:  # noqa: BLE001
        # Don't let scrubbing errors drop events on the floor; return
        # the event unchanged so at least the operator sees *something*.
        return event


# --------------------------------------------------------------------------- #
# Init                                                                         #
# --------------------------------------------------------------------------- #


def init_sentry() -> None:
    """Initialise sentry-sdk from env vars if VOYAGENT_SENTRY_DSN_API is set.

    No-op when the DSN env var is missing (local dev + CI).
    """
    dsn = os.environ.get("VOYAGENT_SENTRY_DSN_API")
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentry-sdk not importable, skipping init: %s", exc)
        return

    integrations: list[Any] = [FastApiIntegration(), StarletteIntegration()]
    try:
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        integrations.append(SqlalchemyIntegration())
    except Exception:  # noqa: BLE001
        pass

    try:
        traces_sample_rate = float(
            os.environ.get("VOYAGENT_SENTRY_TRACES_SAMPLE_RATE", "0.1")
        )
    except ValueError:
        traces_sample_rate = 0.1

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("VOYAGENT_SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("VOYAGENT_VERSION", "0.0.0-dev"),
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,
            integrations=integrations,
            before_send=_before_send,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentry-sdk init failed, continuing without Sentry: %s", exc)


# --------------------------------------------------------------------------- #
# Middleware: tenant tagging + request metrics                                #
# --------------------------------------------------------------------------- #


def _decode_principal_from_bearer(token: str) -> tuple[str | None, str | None]:
    """Best-effort, unverified decode of tenant_id/user_id from a JWT.

    We use this purely for Sentry tagging, so an unverified claim read is
    acceptable — the real auth dependency still does full verification
    before any privileged work happens. Returns (tenant_id, user_id) or
    (None, None) if anything goes wrong.
    """
    try:
        import jwt  # type: ignore[import-not-found]

        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:  # noqa: BLE001
        return None, None
    tenant_id = payload.get("tenant_id") or payload.get("tid")
    user_id = payload.get("sub") or payload.get("user_id")
    return (
        str(tenant_id) if tenant_id is not None else None,
        str(user_id) if user_id is not None else None,
    )


class TenantTaggingMiddleware(BaseHTTPMiddleware):
    """Tag the current Sentry scope with ``tenant_id`` / ``user_id`` and
    record request-level Prometheus metrics.

    Tagging is derived from the ``Authorization: Bearer <jwt>`` header via
    an *unverified* decode. The primary auth dependency still runs full
    verification; this middleware only shapes observability data.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Best-effort Sentry scope tagging.
        tenant_id: str | None = None
        user_id: str | None = None
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            tenant_id, user_id = _decode_principal_from_bearer(
                auth_header.split(" ", 1)[1].strip()
            )

        try:
            import sentry_sdk

            with sentry_sdk.configure_scope() as scope:  # type: ignore[attr-defined]
                if tenant_id:
                    scope.set_tag("tenant_id", tenant_id)
                if user_id:
                    scope.set_tag("user_id", user_id)
        except Exception:  # noqa: BLE001
            pass

        # Metrics: wall-clock the response.
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            try:
                from voyagent_api.metrics import record_request

                record_request(
                    method=request.method,
                    path=request.url.path,
                    status=status_code,
                    duration_seconds=elapsed,
                )
            except Exception:  # noqa: BLE001
                pass


# Backwards-compatible alias used by main.py.
tenant_tagging_middleware = TenantTaggingMiddleware


__all__: Iterable[str] = (
    "init_sentry",
    "TenantTaggingMiddleware",
    "tenant_tagging_middleware",
)
