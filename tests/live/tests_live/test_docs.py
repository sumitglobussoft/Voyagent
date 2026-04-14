from __future__ import annotations

import httpx
import pytest

from ._http import fetch_html

DOC_SLUGS = [
    "ARCHITECTURE",
    "DECISIONS",
    "CANONICAL_MODEL",
    "STACK",
    "ACTIVITIES",
]


@pytest.mark.parametrize("slug", DOC_SLUGS)
async def test_doc_slug_renders(
    session: httpx.AsyncClient, slug: str
) -> None:
    status, body = await fetch_html(session, f"/docs/{slug}")
    assert status == 200, f"/docs/{slug} -> {status}"
    lower = body.lower()
    # Slug title or a recognisable keyword from the source doc.
    assert (
        slug.lower() in lower
        or slug.replace("_", " ").lower() in lower
    ), f"/docs/{slug} body missing slug title"
