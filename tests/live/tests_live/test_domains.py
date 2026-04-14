from __future__ import annotations

import httpx
import pytest

from ._http import fetch_html

DOMAINS = [
    ("/domains/ticketing-visa", "ticketing"),
    ("/domains/hotels-holidays", "hotels"),
    ("/domains/accounting", "accounting"),
]


@pytest.mark.parametrize("path,needle", DOMAINS)
async def test_domain_page_ok(
    session: httpx.AsyncClient, path: str, needle: str
) -> None:
    status, body = await fetch_html(session, path)
    assert status == 200, f"{path} -> {status}"
    assert needle.lower() in body.lower(), (
        f"{path} body missing {needle!r}"
    )
