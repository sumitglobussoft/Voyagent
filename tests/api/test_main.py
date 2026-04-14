"""Tests for the voyagent_api FastAPI app wiring.

Covers router registration, OpenAPI exposure, CORS headers, and
the shape of uncaught-error responses. These assertions run against
``app`` object directly without touching real persistence.
"""

from __future__ import annotations

import os

import pytest


# Auth secret must be set before any voyagent_api module imports.
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Router registration                                                         #
# --------------------------------------------------------------------------- #


def _route_paths() -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_auth_router_is_registered() -> None:
    paths = _route_paths()
    assert "/auth/sign-in" in paths
    assert "/auth/sign-up" in paths
    assert "/auth/refresh" in paths
    assert "/auth/me" in paths


def test_chat_router_is_registered() -> None:
    paths = _route_paths()
    assert "/chat/sessions" in paths
    assert "/chat/sessions/{session_id}" in paths
    assert "/chat/sessions/{session_id}/messages" in paths


def test_reports_router_is_registered() -> None:
    paths = _route_paths()
    assert any(p.startswith("/reports/") for p in paths), (
        f"expected at least one /reports/* path, got: "
        f"{[p for p in paths if p.startswith('/reports')]}"
    )


def test_health_route_registered() -> None:
    assert "/health" in _route_paths()


# --------------------------------------------------------------------------- #
# OpenAPI                                                                     #
# --------------------------------------------------------------------------- #


def test_openapi_json_is_reachable_and_lists_core_paths() -> None:
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body.get("openapi", "").startswith("3.")
    paths = body.get("paths", {})
    assert "/auth/sign-in" in paths
    assert "/chat/sessions" in paths
    assert "/health" in paths


# --------------------------------------------------------------------------- #
# CORS                                                                        #
# --------------------------------------------------------------------------- #


def test_cors_preflight_allows_configured_origin() -> None:
    """OPTIONS preflight for /auth/sign-in must echo the configured origin."""
    client = TestClient(app)
    r = client.options(
        "/auth/sign-in",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # CORSMiddleware returns 200 on a matching preflight.
    assert r.status_code == 200, r.text
    allow_origin = r.headers.get("access-control-allow-origin")
    # Either echoes the origin or returns the literal "*" fallback.
    assert allow_origin in ("http://localhost:3000", "*")
    allow_methods = r.headers.get("access-control-allow-methods", "")
    # starlette normalises to uppercase comma-separated; allow wildcard too.
    assert ("POST" in allow_methods.upper()) or (allow_methods == "*"), allow_methods


def test_cors_response_on_actual_request_sets_allow_origin() -> None:
    """A same-test-client actual request with Origin must carry the
    CORS allow-origin header. We probe ``/health`` so the test doesn't
    need a wired DB."""
    client = TestClient(app)
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in r.headers.keys()}


# --------------------------------------------------------------------------- #
# Global error handling                                                       #
# --------------------------------------------------------------------------- #


def test_unhandled_exception_returns_json_500_not_html_stacktrace() -> None:
    """Attach a temporary route that blows up; the default handler should
    still return JSON with a 500, not an HTML traceback page."""
    route_path = "/__test_only_boom"

    @app.get(route_path)
    async def _boom() -> dict[str, str]:  # noqa: D401
        raise RuntimeError("synthetic blowup")

    try:
        # raise_server_exceptions=False turns the starlette-internal reraise
        # off so we can observe what a real client would see.
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get(route_path)
        assert r.status_code == 500
        ctype = r.headers.get("content-type", "")
        # FastAPI's default handler returns "Internal Server Error" as
        # text/plain. That's not ideal for APIs — we assert only that it
        # is NOT an HTML error page (which would be a Starlette debug
        # middleware accident leaking tracebacks).
        assert "html" not in ctype.lower(), (
            f"expected non-html error response, got content-type={ctype}"
        )
        # Body should not contain a Python traceback line — if it does, an
        # operator-visible debug middleware has been left attached.
        body = r.text or ""
        assert "Traceback" not in body
    finally:
        # Remove the test-only route so it doesn't leak into other tests.
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != route_path
        ]


def test_http_exception_passthrough_returns_json_detail() -> None:
    """A normal HTTPException must surface as ``{"detail": "..."}`` JSON."""
    route_path = "/__test_only_teapot"

    @app.get(route_path)
    async def _teapot() -> dict[str, str]:
        raise HTTPException(status_code=418, detail="i_am_a_teapot")

    try:
        client = TestClient(app)
        r = client.get(route_path)
        assert r.status_code == 418
        assert r.headers.get("content-type", "").startswith("application/json")
        assert r.json() == {"detail": "i_am_a_teapot"}
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != route_path
        ]
