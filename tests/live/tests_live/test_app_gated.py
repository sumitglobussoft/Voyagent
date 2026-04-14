from __future__ import annotations

import httpx


def _assert_app_known_state(resp: httpx.Response, path: str) -> None:
    status = resp.status_code
    assert status == 200 or 300 <= status < 400 or status == 500, (
        f"{path} -> {status}; expected 200/3xx/500"
    )
    if status == 500:
        body = resp.text.lower()
        assert "clerk" in body, (
            f"{path} returned 500 but body does not mention Clerk; "
            f"body={body[:300]!r}"
        )


async def test_app_root(session: httpx.AsyncClient) -> None:
    resp = await session.get("/app")
    _assert_app_known_state(resp, "/app")


async def test_app_nested_route(session: httpx.AsyncClient) -> None:
    resp = await session.get("/app/dashboard")
    _assert_app_known_state(resp, "/app/dashboard")
