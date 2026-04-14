from __future__ import annotations

import httpx
import pytest

from ._http import fetch_html

MARKETING_PATHS = [
    "/",
    "/product",
    "/features",
    "/architecture",
    "/integrations",
    "/security",
    "/pricing",
    "/about",
    "/contact",
]


@pytest.mark.parametrize("path", MARKETING_PATHS)
async def test_marketing_page_ok(
    session: httpx.AsyncClient, path: str
) -> None:
    status, body = await fetch_html(session, path)
    assert status == 200, f"{path} -> {status}"
    lower = body.lower()
    assert "<title>" in lower, f"{path} missing <title>"
    assert "</html>" in lower, f"{path} missing </html>"
    assert "<h1" in lower, f"{path} missing <h1"
    assert len(body) > 3000, (
        f"{path} body too short: {len(body)} bytes"
    )


async def test_landing_contains_tagline(
    session: httpx.AsyncClient,
) -> None:
    _, body = await fetch_html(session, "/")
    assert "Voyagent" in body, "landing missing brand"
    lower = body.lower()
    assert "travel" in lower, "landing missing 'travel' tagline fragment"


async def test_landing_has_meta_description(
    session: httpx.AsyncClient,
) -> None:
    _, body = await fetch_html(session, "/")
    assert 'name="description"' in body.lower() or (
        "meta name=\"description\"" in body.lower()
    ), "landing missing meta description"
