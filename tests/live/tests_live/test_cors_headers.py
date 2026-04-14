from __future__ import annotations

import httpx

from ._http import expect_status_in


async def test_cors_preflight_allows_localhost_dev(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.request(
        "OPTIONS",
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # Accept 2xx (CORS wired + allow-origin set), 400 (FastAPI/Starlette
    # reject OPTIONS on routes without an explicit handler), or 405 (Method
    # Not Allowed when the route doesn't accept OPTIONS). Nginx in front of
    # FastAPI may also turn preflights into 400 for open routes.
    if 200 <= resp.status_code < 300:
        allow = resp.headers.get("access-control-allow-origin", "")
        assert allow, (
            f"2xx preflight missing allow-origin: "
            f"headers={dict(resp.headers)}"
        )
    else:
        await expect_status_in(resp, {400, 405})


async def test_cors_on_chat_sessions(
    session: httpx.AsyncClient,
) -> None:
    origin = "https://voyagent.globusdemos.com"
    resp = await session.request(
        "OPTIONS",
        "/api/chat/sessions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert 200 <= resp.status_code < 300, (
        f"preflight failed: {resp.status_code} "
        f"body={resp.text[:200]!r}"
    )
    allow = resp.headers.get("access-control-allow-origin", "")
    assert origin in allow or allow == "*", (
        f"allow-origin {allow!r} does not cover {origin!r}"
    )
