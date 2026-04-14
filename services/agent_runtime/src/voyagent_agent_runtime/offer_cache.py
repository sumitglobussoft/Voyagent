"""Concrete :class:`OfferCache` implementations for the agent runtime.

The Protocol itself lives in :mod:`drivers._contracts.cache` so drivers
can depend on the shape without pulling in the runtime. This module
adds two concrete back-ends:

* :class:`InMemoryOfferCache` — dict-backed with a min-heap for TTL
  eviction. Used in unit tests and single-process local dev.
* :class:`RedisOfferCache` — ``redis.asyncio``-backed. Production
  deployments point at the Redis in ``infra/docker/dev.yml``.

Pick between them with :func:`build_offer_cache` based on whether
``VOYAGENT_REDIS_URL`` is configured.
"""

from __future__ import annotations

import heapq
import json
import logging
import os
import time
from typing import Any

from drivers._contracts.cache import OfferCache

logger = logging.getLogger(__name__)


DEFAULT_REDIS_URL = "redis://localhost:6379/0"
REDIS_KEY_PREFIX = "voyagent:offer:"


# --------------------------------------------------------------------------- #
# In-memory                                                                   #
# --------------------------------------------------------------------------- #


class InMemoryOfferCache:
    """Non-persistent :class:`OfferCache` for tests and local dev.

    TTL is enforced lazily: each ``put`` appends a ``(expires_at, key)``
    tuple to a min-heap and every ``get`` sweeps expired entries off
    the top. This is O(log n) for ``put`` and amortised O(1) for
    ``get``, which is more than enough for unit tests.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}
        self._expiry_heap: list[tuple[float, str]] = []

    def _now(self) -> float:
        return time.time()

    def _sweep(self) -> None:
        now = self._now()
        while self._expiry_heap and self._expiry_heap[0][0] <= now:
            _, key = heapq.heappop(self._expiry_heap)
            entry = self._store.get(key)
            if entry is not None and entry[0] <= now:
                self._store.pop(key, None)

    async def put(
        self, key: str, offer: dict[str, Any], *, ttl_seconds: int
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        expires_at = self._now() + ttl_seconds
        self._store[key] = (expires_at, dict(offer))
        heapq.heappush(self._expiry_heap, (expires_at, key))

    async def get(self, key: str) -> dict[str, Any] | None:
        self._sweep()
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, offer = entry
        if expires_at <= self._now():
            self._store.pop(key, None)
            return None
        # Return a shallow copy so callers that mutate the dict don't
        # poison the cache.
        return dict(offer)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


# --------------------------------------------------------------------------- #
# Redis                                                                       #
# --------------------------------------------------------------------------- #


class RedisOfferCache:
    """Production :class:`OfferCache` backed by Redis.

    Values are serialised as JSON and namespaced under
    ``voyagent:offer:`` so the same Redis instance can host other
    Voyagent caches without collisions. ``redis.asyncio`` is loaded
    lazily so test environments that don't install redis still import
    this module.
    """

    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("VOYAGENT_REDIS_URL", DEFAULT_REDIS_URL)
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as redis  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — env-dependent
            raise RuntimeError(
                "redis is not installed; add redis[hiredis] to the "
                "agent_runtime deps or configure an in-memory cache."
            ) from exc
        self._client = redis.from_url(self._url, decode_responses=True)
        return self._client

    @staticmethod
    def _redis_key(key: str) -> str:
        return f"{REDIS_KEY_PREFIX}{key}"

    async def put(
        self, key: str, offer: dict[str, Any], *, ttl_seconds: int
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        client = self._ensure_client()
        await client.set(
            self._redis_key(key), json.dumps(offer), ex=ttl_seconds
        )

    async def get(self, key: str) -> dict[str, Any] | None:
        client = self._ensure_client()
        raw = await client.get(self._redis_key(key))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "offer cache: non-JSON payload at %s — evicting", key
            )
            await self.delete(key)
            return None
        if not isinstance(data, dict):
            logger.warning(
                "offer cache: non-object payload at %s — evicting", key
            )
            await self.delete(key)
            return None
        return data

    async def delete(self, key: str) -> None:
        client = self._ensure_client()
        await client.delete(self._redis_key(key))

    async def aclose(self) -> None:
        """Release the underlying Redis connection."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except AttributeError:  # pragma: no cover - older redis
                await self._client.close()
            self._client = None


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


def build_offer_cache(redis_url: str | None = None) -> OfferCache:
    """Return a :class:`RedisOfferCache` if a URL is available, else in-memory.

    The URL comes from ``VOYAGENT_REDIS_URL`` when the argument is
    omitted. Passing an explicit empty string forces in-memory.
    """
    url = redis_url if redis_url is not None else os.environ.get("VOYAGENT_REDIS_URL")
    if not url:
        logger.info("offer cache: no VOYAGENT_REDIS_URL — using in-memory cache")
        return InMemoryOfferCache()
    return RedisOfferCache(url)


__all__ = [
    "DEFAULT_REDIS_URL",
    "InMemoryOfferCache",
    "OfferCache",
    "REDIS_KEY_PREFIX",
    "RedisOfferCache",
    "build_offer_cache",
]
