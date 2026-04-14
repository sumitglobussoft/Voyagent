from __future__ import annotations

import json
from typing import Any

import httpx


def _preview(body: str, limit: int = 240) -> str:
    body = body.replace("\n", " ").strip()
    return body[:limit] + ("..." if len(body) > limit else "")


async def expect_status_in(
    resp: httpx.Response,
    allowed: set[int],
    msg: str | None = None,
) -> None:
    if resp.status_code in allowed:
        return
    try:
        body = resp.text
    except Exception:  # noqa: BLE001
        body = "<unreadable>"
    detail = (
        f"{msg + ': ' if msg else ''}"
        f"{resp.request.method} {resp.request.url} "
        f"-> {resp.status_code}; expected one of {sorted(allowed)}; "
        f"body={_preview(body)!r}"
    )
    raise AssertionError(detail)


async def fetch_html(
    client: httpx.AsyncClient, path: str
) -> tuple[int, str]:
    resp = await client.get(path)
    ctype = resp.headers.get("content-type", "")
    if not ctype.lower().startswith("text/html"):
        raise AssertionError(
            f"GET {path} -> {resp.status_code}; "
            f"expected text/html, got content-type={ctype!r}; "
            f"body={_preview(resp.text)!r}"
        )
    return resp.status_code, resp.text


async def parse_json(resp: httpx.Response) -> dict[str, Any]:
    ctype = resp.headers.get("content-type", "")
    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        body = resp.text
        if "<html" in body.lower() or "<!doctype" in body.lower():
            raise AssertionError(
                f"Expected JSON from {resp.request.url} but got HTML "
                f"(likely Cloudflare interstitial). "
                f"status={resp.status_code} ctype={ctype!r} "
                f"body={_preview(body)!r}"
            ) from exc
        raise AssertionError(
            f"Invalid JSON from {resp.request.url} "
            f"status={resp.status_code} ctype={ctype!r} "
            f"body={_preview(body)!r}"
        ) from exc
