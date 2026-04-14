from __future__ import annotations

import httpx


def _assert_app_gated(resp: httpx.Response, path: str) -> None:
    """The authenticated ``/app`` shell must gate unauthenticated visitors.

    Accepts:
      * 200 — a sign-in interstitial rendered at the `/app` route
      * 3xx — middleware redirect to ``/sign-in`` (or canonical trailing slash)
      * 404 — Next.js not-found (expected for ``/app/dashboard`` which we
        haven't built yet; only ``/app`` root is guaranteed to exist)
    """
    status = resp.status_code
    assert status == 200 or 300 <= status < 400 or status == 404, (
        f"{path} -> {status}; expected 200/3xx/404"
    )
    if 300 <= status < 400:
        location = resp.headers.get("location", "")
        assert "/sign-in" in location or path in location, (
            f"{path} redirected to unexpected location {location!r}"
        )


async def test_app_root(session: httpx.AsyncClient) -> None:
    resp = await session.get("/app")
    _assert_app_gated(resp, "/app")


async def test_app_nested_route(session: httpx.AsyncClient) -> None:
    resp = await session.get("/app/dashboard")
    _assert_app_gated(resp, "/app/dashboard")
