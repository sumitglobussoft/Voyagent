"""Tests for :class:`voyagent_agent_runtime.tool_cache.ToolResultCache`."""

from __future__ import annotations

import pytest

from voyagent_agent_runtime.tool_cache import (
    CACHEABLE_TOOLS,
    ToolResultCache,
)

pytestmark = pytest.mark.asyncio


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_allowlist_includes_read_only_tools() -> None:
    # Smoke: the explicit set from the spec.
    assert "search_flights" in CACHEABLE_TOOLS
    assert "search_hotels" in CACHEABLE_TOOLS
    assert "check_hotel_rate" in CACHEABLE_TOOLS
    assert "list_ledger_accounts" in CACHEABLE_TOOLS
    assert "lookup_passenger" in CACHEABLE_TOOLS


async def test_write_side_tools_are_not_cacheable() -> None:
    assert "issue_ticket" not in CACHEABLE_TOOLS
    assert "book_hotel" not in CACHEABLE_TOOLS
    assert "post_journal_entry" not in CACHEABLE_TOOLS
    assert "draft_invoice" not in CACHEABLE_TOOLS


async def test_hit_on_same_args_same_tenant() -> None:
    clock = _FakeClock()
    cache = ToolResultCache(default_ttl=300.0, time_fn=clock)
    args = {"origin": "DEL", "destination": "DXB"}
    assert await cache.get("tenant-a", "search_flights", args) is None
    await cache.put(
        "tenant-a", "search_flights", args, {"fares": [{"id": "F1"}]}
    )
    hit = await cache.get("tenant-a", "search_flights", args)
    assert hit == {"fares": [{"id": "F1"}]}
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


async def test_different_args_do_not_hit() -> None:
    cache = ToolResultCache()
    await cache.put(
        "tenant-a", "search_flights", {"origin": "DEL"}, {"fares": [1]}
    )
    miss = await cache.get(
        "tenant-a", "search_flights", {"origin": "BOM"}
    )
    assert miss is None


async def test_write_side_tool_is_never_cached() -> None:
    cache = ToolResultCache()
    await cache.put(
        "tenant-a", "issue_ticket", {"pnr": "ABC123"}, {"ok": True}
    )
    # put is a no-op for non-cacheable tools, so get should miss.
    hit = await cache.get("tenant-a", "issue_ticket", {"pnr": "ABC123"})
    assert hit is None


async def test_tenant_scoped_isolation() -> None:
    cache = ToolResultCache()
    args = {"origin": "DEL"}
    await cache.put(
        "tenant-a", "search_flights", args, {"fares": ["a-only"]}
    )
    assert (
        await cache.get("tenant-b", "search_flights", args)
    ) is None
    hit = await cache.get("tenant-a", "search_flights", args)
    assert hit == {"fares": ["a-only"]}


async def test_ttl_expiry() -> None:
    clock = _FakeClock(start=1000.0)
    cache = ToolResultCache(default_ttl=60.0, time_fn=clock)
    args = {"k": 1}
    await cache.put("tenant-a", "search_flights", args, {"v": 1})
    assert await cache.get("tenant-a", "search_flights", args) == {"v": 1}
    clock.advance(61.0)
    assert await cache.get("tenant-a", "search_flights", args) is None


async def test_per_tool_ttl_override_shorter() -> None:
    clock = _FakeClock(start=0.0)
    cache = ToolResultCache(default_ttl=300.0, time_fn=clock)
    # check_hotel_rate has a 120s TTL override — still fresh at 119s.
    await cache.put(
        "tenant-a", "check_hotel_rate", {"id": 1}, {"rate": "100"}
    )
    clock.advance(119.0)
    assert await cache.get(
        "tenant-a", "check_hotel_rate", {"id": 1}
    ) == {"rate": "100"}
    clock.advance(2.0)
    assert await cache.get(
        "tenant-a", "check_hotel_rate", {"id": 1}
    ) is None


async def test_input_order_does_not_affect_hash() -> None:
    cache = ToolResultCache()
    await cache.put(
        "tenant-a",
        "search_flights",
        {"origin": "DEL", "destination": "DXB"},
        {"v": 1},
    )
    # Same args, different key order — must hit.
    hit = await cache.get(
        "tenant-a",
        "search_flights",
        {"destination": "DXB", "origin": "DEL"},
    )
    assert hit == {"v": 1}
