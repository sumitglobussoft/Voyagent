"""Pooled Playwright browser contexts.

The pool keeps at most ``max_concurrency`` contexts alive. Contexts are
keyed by ``(tenant_id, namespace)`` so VFS sessions (which are expensive
to re-establish — portal login + CAPTCHA + MFA) survive across jobs for
the same tenant while staying isolated from other tenants.

Idle contexts are evicted after ``context_idle_eviction_seconds`` to
keep memory use bounded on long-running workers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from schemas.canonical import EntityId

if TYPE_CHECKING:
    from .settings import BrowserRunnerSettings

logger = logging.getLogger(__name__)


class _PooledContext:
    """Internal record: one Playwright browser context + bookkeeping."""

    __slots__ = ("context", "last_used", "in_use", "lock")

    def __init__(self, context: Any) -> None:
        self.context = context
        self.last_used = time.monotonic()
        self.in_use = False
        # Guards concurrent acquisitions of the *same* tenant+namespace —
        # Playwright contexts are not safe for concurrent use across tabs.
        self.lock = asyncio.Lock()


class BrowserPool:
    """Maintains a small pool of Playwright browser contexts."""

    def __init__(self, settings: "BrowserRunnerSettings") -> None:
        self._settings = settings
        self._contexts: dict[tuple[EntityId, str], _PooledContext] = {}
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch Playwright + the configured browser. Idempotent."""
        if self._playwright is not None:
            return
        # Imported lazily so tests can swap the pool for a fake without
        # needing Playwright installed.
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._settings.browser)
        self._browser = await launcher.launch(headless=self._settings.headless)
        logger.info(
            "browser_pool.started",
            extra={
                "browser": self._settings.browser,
                "headless": self._settings.headless,
                "max_concurrency": self._settings.max_concurrency,
            },
        )

    async def _evict_stale_locked(self) -> None:
        """Drop idle contexts; caller must hold ``self._lock``."""
        now = time.monotonic()
        ttl = self._settings.context_idle_eviction_seconds
        stale: list[tuple[EntityId, str]] = []
        for key, pooled in self._contexts.items():
            if pooled.in_use:
                continue
            if now - pooled.last_used > ttl:
                stale.append(key)
        for key in stale:
            pooled = self._contexts.pop(key)
            try:
                await pooled.context.close()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "browser_pool.evict_close_failed",
                    extra={"tenant_id": key[0], "namespace": key[1]},
                    exc_info=True,
                )
            logger.info(
                "browser_pool.evicted",
                extra={"tenant_id": key[0], "namespace": key[1]},
            )

    async def _get_or_create(self, key: tuple[EntityId, str]) -> _PooledContext:
        async with self._lock:
            await self._evict_stale_locked()
            pooled = self._contexts.get(key)
            if pooled is not None:
                return pooled
            if (
                sum(1 for p in self._contexts.values() if not p.in_use) == 0
                and len(self._contexts) >= self._settings.max_concurrency
            ):
                # Evict the oldest idle entry if any, else raise.
                idle = [
                    (k, p) for k, p in self._contexts.items() if not p.in_use
                ]
                if not idle:
                    raise RuntimeError(
                        "browser pool exhausted — all contexts are in use. "
                        "Increase VOYAGENT_BROWSER_MAX_CONCURRENCY."
                    )
                idle.sort(key=lambda kv: kv[1].last_used)
                victim_key, victim = idle[0]
                self._contexts.pop(victim_key)
                try:
                    await victim.context.close()
                except Exception:  # noqa: BLE001
                    logger.warning("browser_pool.lru_close_failed", exc_info=True)
            if self._browser is None:
                await self.start()
            context = await self._browser.new_context()
            pooled = _PooledContext(context)
            self._contexts[key] = pooled
            logger.info(
                "browser_pool.context_created",
                extra={"tenant_id": key[0], "namespace": key[1]},
            )
            return pooled

    @asynccontextmanager
    async def acquire(
        self, tenant_id: EntityId, namespace: str
    ) -> AsyncIterator[Any]:
        """Acquire a :class:`Page` bound to a tenant+namespace context.

        The context is reused across jobs for the same key, preserving
        cookies and storage — essential for visa portals where login is
        expensive and sometimes rate-limited.
        """
        key = (tenant_id, namespace)
        pooled = await self._get_or_create(key)
        async with pooled.lock:
            pooled.in_use = True
            try:
                page = await pooled.context.new_page()
                try:
                    yield page
                finally:
                    try:
                        await page.close()
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "browser_pool.page_close_failed",
                            extra={"tenant_id": tenant_id, "namespace": namespace},
                            exc_info=True,
                        )
            finally:
                pooled.in_use = False
                pooled.last_used = time.monotonic()

    async def aclose(self) -> None:
        """Close every context, the browser, and the Playwright instance."""
        for key, pooled in list(self._contexts.items()):
            try:
                await pooled.context.close()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "browser_pool.close_context_failed",
                    extra={"tenant_id": key[0], "namespace": key[1]},
                    exc_info=True,
                )
        self._contexts.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                logger.warning("browser_pool.close_browser_failed", exc_info=True)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                logger.warning("browser_pool.stop_playwright_failed", exc_info=True)
            self._playwright = None


__all__ = ["BrowserPool"]
