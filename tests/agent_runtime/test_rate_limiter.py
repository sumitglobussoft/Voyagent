"""Tests for :class:`voyagent_agent_runtime.rate_limiter.InMemoryRateLimiter`."""

from __future__ import annotations

import pytest

from voyagent_agent_runtime.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitExceededError,
)

pytestmark = pytest.mark.asyncio


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_allows_under_the_limit() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    for _ in range(5):
        await limiter.check("tenant-a", per_minute=5, per_hour=100)


async def test_rejects_when_minute_limit_exceeded() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    for _ in range(3):
        await limiter.check("tenant-a", per_minute=3, per_hour=100)
    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check("tenant-a", per_minute=3, per_hour=100)
    assert exc_info.value.scope == "minute"
    assert exc_info.value.tenant_id == "tenant-a"


async def test_rejects_when_hour_limit_exceeded() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    # Scatter calls across minutes so per_minute never trips.
    for i in range(4):
        clock.advance(120.0)  # 2 minutes between calls
        await limiter.check("tenant-a", per_minute=10, per_hour=4)
    with pytest.raises(RateLimitExceededError) as exc_info:
        clock.advance(120.0)
        await limiter.check("tenant-a", per_minute=10, per_hour=4)
    assert exc_info.value.scope == "hour"


async def test_sliding_window_drops_old_entries() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    for _ in range(5):
        await limiter.check("tenant-a", per_minute=5, per_hour=100)
    # 5th call should fail until the window slides.
    with pytest.raises(RateLimitExceededError):
        await limiter.check("tenant-a", per_minute=5, per_hour=100)
    # Advance past the 60s minute window — old entries prune and the
    # limiter accepts a new call.
    clock.advance(61.0)
    await limiter.check("tenant-a", per_minute=5, per_hour=100)


async def test_two_tenants_do_not_share_quota() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    for _ in range(3):
        await limiter.check("tenant-a", per_minute=3, per_hour=100)
    # tenant-a is exhausted but tenant-b must still be accepted.
    for _ in range(3):
        await limiter.check("tenant-b", per_minute=3, per_hour=100)
    with pytest.raises(RateLimitExceededError):
        await limiter.check("tenant-a", per_minute=3, per_hour=100)


async def test_reset_clears_history() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(time_fn=clock)
    for _ in range(3):
        await limiter.check("tenant-a", per_minute=3, per_hour=100)
    limiter.reset("tenant-a")
    # Fresh quota after reset.
    for _ in range(3):
        await limiter.check("tenant-a", per_minute=3, per_hour=100)
