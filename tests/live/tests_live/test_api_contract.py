from __future__ import annotations

import httpx

from ._http import expect_status_in, parse_json


async def test_schemas_money(session: httpx.AsyncClient) -> None:
    resp = await session.get("/api/schemas/money")
    await expect_status_in(resp, {200})
    data = await parse_json(resp)
    assert isinstance(data, dict), f"expected dict, got {type(data)}"
    assert "type" in data or "properties" in data, (
        f"schema missing type/properties: keys={list(data.keys())}"
    )
    if "properties" in data:
        props = data["properties"]
        assert isinstance(props, dict)
        assert "amount" in props, f"missing amount in {list(props)}"
        assert "currency" in props, f"missing currency in {list(props)}"


async def test_api_health_routes(session: httpx.AsyncClient) -> None:
    r1 = await session.get("/api/health")
    await expect_status_in(r1, {200})
    r2 = await session.get("/health")
    await expect_status_in(r2, {200})
