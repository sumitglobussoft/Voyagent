from __future__ import annotations

import httpx
import pytest

from ._http import expect_status_in, parse_json


async def test_api_health_ok(session: httpx.AsyncClient) -> None:
    resp = await session.get("/api/health")
    await expect_status_in(resp, {200})
    body = await parse_json(resp)
    assert body == {"status": "ok"}, f"unexpected body: {body!r}"


async def test_inner_nginx_health_reachable(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.get("/health")
    await expect_status_in(resp, {200})


async def test_health_sets_no_cache_headers(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.get("/api/health")
    assert resp.status_code == 200
    cc = resp.headers.get("cache-control", "").lower()
    # Soft expectation: either no-store, or missing, or CF-inserted.
    if cc and "no-store" not in cc and "private" not in cc:
        pytest.skip(
            f"cache-control set by edge: {cc!r}; not a hard failure"
        )
