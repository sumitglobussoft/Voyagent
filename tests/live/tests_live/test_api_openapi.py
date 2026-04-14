from __future__ import annotations

import httpx

from ._http import parse_json


async def test_openapi_json_reachable(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.get("/api/openapi.json")
    if resp.status_code != 200:
        resp = await session.get("/openapi.json")
    assert resp.status_code == 200, (
        f"openapi not reachable: {resp.status_code}"
    )
    data = await parse_json(resp)
    assert "openapi" in data, f"missing 'openapi' key: {list(data)}"
    assert str(data["openapi"]).startswith("3."), (
        f"unexpected openapi version: {data['openapi']!r}"
    )
    assert isinstance(data.get("paths"), dict), (
        "'paths' missing or not a dict"
    )


async def test_openapi_contains_chat_routes(
    session: httpx.AsyncClient,
) -> None:
    resp = await session.get("/api/openapi.json")
    if resp.status_code != 200:
        resp = await session.get("/openapi.json")
    assert resp.status_code == 200
    data = await parse_json(resp)
    paths = data.get("paths", {})
    assert "/chat/sessions" in paths, (
        f"missing /chat/sessions in {list(paths)}"
    )
    assert "/chat/sessions/{session_id}/messages" in paths, (
        "missing /chat/sessions/{session_id}/messages"
    )
