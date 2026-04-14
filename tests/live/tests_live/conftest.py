from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

BASE_URL = os.environ.get(
    "VOYAGENT_BASE_URL", "https://voyagent.globusdemos.com"
).rstrip("/")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "contract: long-running or slower contract-level live tests",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail fast if the target is unreachable."""
    url = f"{BASE_URL}/api/health"
    try:
        resp = httpx.get(url, timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"Target {BASE_URL} unreachable: {exc!r}", returncode=2
        )
        return
    if resp.status_code // 100 != 2:
        pytest.exit(
            f"Target {BASE_URL} unreachable: /api/health returned "
            f"{resp.status_code}",
            returncode=2,
        )


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest_asyncio.fixture(scope="session")
async def session() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(20.0, connect=5.0),
        follow_redirects=False,
        headers={"User-Agent": "voyagent-live-tests/0.1"},
    ) as client:
        yield client
