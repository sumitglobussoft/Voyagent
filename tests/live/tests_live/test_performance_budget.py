from __future__ import annotations

import time
import warnings

import httpx
import pytest


@pytest.mark.contract
async def test_landing_under_15_seconds(
    session: httpx.AsyncClient,
) -> None:
    start = time.monotonic()
    resp = await session.get("/")
    elapsed = time.monotonic() - start
    assert resp.status_code == 200, f"landing -> {resp.status_code}"
    if elapsed > 10:
        warnings.warn(
            f"landing slow: {elapsed:.2f}s (budget 15s)",
            stacklevel=1,
        )
    assert elapsed < 15, f"landing took {elapsed:.2f}s (>15s)"


async def test_api_health_fast(session: httpx.AsyncClient) -> None:
    start = time.monotonic()
    resp = await session.get("/api/health")
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    assert elapsed < 3, f"/api/health took {elapsed:.2f}s (>3s budget)"
