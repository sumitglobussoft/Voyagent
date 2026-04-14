"""Fixtures for the browser-runner test suite.

All fixtures are in-memory: no Redis, no real browser, no S3. Tests that
need a real browser should go under pytest-playwright integration tests
(not shipped in v0).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from voyagent_browser_runner import (
    BrowserRunnerSettings,
    InMemoryArtifactSink,
    InMemoryJobQueue,
)


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


@pytest.fixture
def tenant_id() -> str:
    return _uuid7_like()


@pytest.fixture
def job_id() -> str:
    return _uuid7_like()


@pytest.fixture
def in_memory_queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def in_memory_artifacts() -> InMemoryArtifactSink:
    return InMemoryArtifactSink()


@pytest.fixture
def browser_settings() -> BrowserRunnerSettings:
    """Settings safe for tests — tight timeouts, no retries."""
    return BrowserRunnerSettings(
        redis_url="redis://unused.invalid/1",
        queue_name="voyagent:test_jobs",
        result_ttl_seconds=60,
        max_concurrency=1,
        headless=True,
        browser="chromium",
        artifact_bucket="test-bucket",
        artifact_endpoint=None,
        retry_limit=1,
        job_timeout_seconds=5,
        context_idle_eviction_seconds=60,
    )


# --------------------------------------------------------------------------- #
# Fake Playwright surface                                                     #
# --------------------------------------------------------------------------- #


class FakeElement:
    """Duck-typed Playwright element handle.

    Implements the subset used by :mod:`voyagent_browser_runner.steps`
    and the VFS handlers.
    """

    def __init__(
        self,
        *,
        text: str = "",
        attributes: dict[str, str] | None = None,
        children: dict[str, "FakeElement"] | None = None,
    ) -> None:
        self._text = text
        self._attributes = attributes or {}
        self._children = children or {}
        self.click_count = 0

    async def text_content(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._attributes.get(name)

    async def query_selector(self, selector: str) -> "FakeElement | None":
        return self._children.get(selector)

    async def click(self) -> None:
        self.click_count += 1


class FakePage:
    """Duck-typed Playwright Page.

    Only the methods exercised by ``steps.py`` and the VFS handlers are
    implemented. Behaviours are programmed by populating the mutable
    ``selectors`` / ``selector_lists`` / ``content`` attributes before
    the test calls a handler.
    """

    def __init__(self) -> None:
        self.current_url: str | None = None
        self.url_history: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.raise_on_goto: Exception | None = None
        self.selectors: dict[str, FakeElement] = {}
        self.selector_lists: dict[str, list[FakeElement]] = {}
        self.texts: dict[str, str] = {}
        self.screenshot_bytes: bytes = b"\x89PNG\r\n\x1a\nfake"
        self.html: str = "<html><body>ok</body></html>"

    async def goto(self, url: str, timeout: int | None = None) -> None:
        if self.raise_on_goto is not None:
            raise self.raise_on_goto
        self.current_url = url
        self.url_history.append(url)

    async def click(self, selector: str, timeout: int | None = None) -> None:
        self.clicks.append(selector)

    async def fill(self, selector: str, value: str, timeout: int | None = None) -> None:
        self.fills.append((selector, value))

    async def wait_for_selector(
        self, selector: str, state: str = "visible", timeout: int | None = None
    ) -> None:
        return None

    async def set_input_files(self, selector: str, path: str) -> None:
        self.uploads.append((selector, path))

    async def text_content(self, selector: str, timeout: int | None = None) -> str:
        return self.texts.get(selector, "")

    async def query_selector_all(self, selector: str) -> list[FakeElement]:
        return self.selector_lists.get(selector, [])

    async def screenshot(self, full_page: bool = False) -> bytes:
        return self.screenshot_bytes

    async def content(self) -> str:
        return self.html

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_page() -> FakePage:
    return FakePage()


# --------------------------------------------------------------------------- #
# Fake browser pool                                                           #
# --------------------------------------------------------------------------- #


class FakeBrowserPool:
    """Hands out a :class:`FakePage` when :meth:`acquire` is called.

    Mirrors the :class:`BrowserPool` surface the worker uses. Holds a
    single page instance so tests can inspect its state after the
    handler runs.
    """

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.started = False
        self.closed = False
        self.acquisitions: list[tuple[str, str]] = []

    async def start(self) -> None:
        self.started = True

    def acquire(self, tenant_id: str, namespace: str):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            self.acquisitions.append((tenant_id, namespace))
            yield self.page

        return _cm()

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_browser_pool(fake_page: FakePage) -> FakeBrowserPool:
    return FakeBrowserPool(fake_page)


@pytest.fixture(autouse=True)
def _restore_handler_registry():
    """Snapshot and restore the handler registry around every test.

    Tests re-register kinds with stub handlers; without this the
    builtin VFS handlers would be permanently replaced after the first
    test that tweaks them.
    """
    from voyagent_browser_runner.handlers import _REGISTRY

    snapshot = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)

