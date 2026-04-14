"""Tests for the in-memory offer cache.

Redis-backed tests are skipped unless ``VOYAGENT_REDIS_URL`` is
exported — this suite runs on any laptop without Redis installed.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from voyagent_agent_runtime.offer_cache import (
    InMemoryOfferCache,
    build_offer_cache,
)

pytestmark = pytest.mark.asyncio


async def test_put_get_round_trip() -> None:
    cache = InMemoryOfferCache()
    await cache.put("k", {"a": 1}, ttl_seconds=60)
    assert await cache.get("k") == {"a": 1}


async def test_get_returns_none_when_missing() -> None:
    cache = InMemoryOfferCache()
    assert await cache.get("nope") is None


async def test_delete_removes_entry() -> None:
    cache = InMemoryOfferCache()
    await cache.put("k", {"a": 1}, ttl_seconds=60)
    await cache.delete("k")
    assert await cache.get("k") is None


async def test_ttl_eviction() -> None:
    cache = InMemoryOfferCache()

    # Monkey-patch ``_now`` so we don't actually wait.
    fake_now = [1000.0]

    def _now() -> float:
        return fake_now[0]

    cache._now = _now  # type: ignore[method-assign]

    await cache.put("k", {"a": 1}, ttl_seconds=10)
    assert await cache.get("k") == {"a": 1}

    fake_now[0] = 1011.0  # past expiry
    assert await cache.get("k") is None


async def test_put_rejects_non_positive_ttl() -> None:
    cache = InMemoryOfferCache()
    with pytest.raises(ValueError):
        await cache.put("k", {"a": 1}, ttl_seconds=0)
    with pytest.raises(ValueError):
        await cache.put("k", {"a": 1}, ttl_seconds=-5)


async def test_get_returns_defensive_copy() -> None:
    """Mutating the returned dict must not poison subsequent reads."""
    cache = InMemoryOfferCache()
    await cache.put("k", {"inner": "v"}, ttl_seconds=60)
    first = await cache.get("k")
    assert first is not None
    first["inner"] = "mutated"
    second = await cache.get("k")
    assert second == {"inner": "v"}


async def test_build_offer_cache_in_memory_when_no_url() -> None:
    cache = build_offer_cache(None)
    assert isinstance(cache, InMemoryOfferCache)


@pytest.mark.skipif(
    not os.environ.get("VOYAGENT_REDIS_URL"),
    reason="VOYAGENT_REDIS_URL not set — skipping live Redis test.",
)
async def test_build_offer_cache_redis_when_url_present() -> None:
    from voyagent_agent_runtime.offer_cache import RedisOfferCache

    cache = build_offer_cache(os.environ["VOYAGENT_REDIS_URL"])
    assert isinstance(cache, RedisOfferCache)
    await cache.put("k", {"a": 1}, ttl_seconds=2)
    assert await cache.get("k") == {"a": 1}
    await asyncio.sleep(0)  # let aiohttp event loop flush
    await cache.delete("k")
    await cache.aclose()
