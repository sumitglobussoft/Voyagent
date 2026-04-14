from __future__ import annotations

import httpx

from ._http import expect_status_in


async def test_robots_txt(session: httpx.AsyncClient) -> None:
    resp = await session.get("/robots.txt")
    await expect_status_in(resp, {200})
    ctype = resp.headers.get("content-type", "").lower()
    assert "text/plain" in ctype, f"unexpected content-type: {ctype!r}"
    # Next's default robots emitter writes `User-Agent` (capital-A).
    assert "user-agent" in resp.text.lower(), "robots.txt missing user-agent"


async def test_sitemap_xml(session: httpx.AsyncClient) -> None:
    resp = await session.get("/sitemap.xml")
    await expect_status_in(resp, {200})
    ctype = resp.headers.get("content-type", "").lower()
    assert "xml" in ctype, f"unexpected content-type: {ctype!r}"
    body = resp.text
    assert "<urlset" in body, "sitemap missing <urlset"
    assert "voyagent" in body.lower(), (
        "sitemap missing landing URL fragment"
    )


async def test_favicon_reachable(session: httpx.AsyncClient) -> None:
    resp = await session.get("/favicon.svg")
    await expect_status_in(resp, {200, 304})


async def test_og_image_reachable(session: httpx.AsyncClient) -> None:
    resp = await session.get("/og-image.svg")
    await expect_status_in(resp, {200, 304})
