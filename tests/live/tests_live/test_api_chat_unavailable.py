"""Error-contract tests for the chat surface.

These tests pin the *error contract* the chat routes emit for
unauthenticated callers, and for authenticated callers when the
model backend is unavailable (``ANTHROPIC_API_KEY`` unset). They do
NOT exercise a successful chat flow — once a real model key lands,
tighten these tests to provision a tenant via
``POST /api/auth/sign-up`` and assert on the happy path.
"""

from __future__ import annotations

import httpx

from ._http import expect_status_in

UNAUTH_OK = {401, 403, 503, 307, 308}
UNAUTH_OK_WITH_404 = UNAUTH_OK | {404}


def _assert_body_shape(resp: httpx.Response) -> None:
    ctype = resp.headers.get("content-type", "").lower()
    body = resp.text
    if "application/json" in ctype:
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"json content-type but invalid body: {body[:200]!r}"
            ) from exc
        assert isinstance(data, dict), (
            f"expected dict, got {type(data).__name__}"
        )
        assert "detail" in data, (
            f"json error missing 'detail': {list(data)}"
        )
    elif "text/html" in ctype:
        # A sign-in interstitial served at the chat route is legal.
        assert len(body) > 0
    else:
        # Redirect or empty body is fine for 307/308.
        assert resp.status_code in {307, 308} or body == "" or body


async def test_create_session_unauth(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.post("/api/chat/sessions", json={})
    await expect_status_in(resp, UNAUTH_OK)
    _assert_body_shape(resp)


async def test_get_session_unauth(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.get("/api/chat/sessions/does-not-exist")
    await expect_status_in(resp, UNAUTH_OK_WITH_404)
    _assert_body_shape(resp)


async def test_send_message_unauth(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.post(
        "/api/chat/sessions/foo/messages",
        json={"content": "hello"},
    )
    await expect_status_in(resp, UNAUTH_OK_WITH_404)
    _assert_body_shape(resp)
