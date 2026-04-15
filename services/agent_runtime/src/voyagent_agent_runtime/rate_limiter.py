"""Per-tenant sliding-window rate limiter.

Process-local, in-memory. Each tenant has two windows: a 60-second and
a 3600-second one. On every :meth:`check` call we prune entries older
than the widest window, then compare counts against the passed-in
limits. The widest-window prune keeps memory bounded.

Matches the pattern used by the marketing contact-form limiter
(``apps/marketing/app/api/contact/_limiter.ts``) — deliberately simple,
process-local, not a distributed quota service. Multi-process
deployments should front this with Redis once the shape stabilises.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Protocol


class RateLimitExceededError(Exception):
    """Raised when a tenant exceeds its per-minute or per-hour quota."""

    def __init__(self, tenant_id: str, scope: str) -> None:
        super().__init__(f"rate_limited: tenant={tenant_id} scope={scope}")
        self.tenant_id = tenant_id
        self.scope = scope


class RateLimiter(Protocol):
    async def check(
        self, tenant_id: str, per_minute: int, per_hour: int
    ) -> None: ...


_MINUTE = 60.0
_HOUR = 3600.0


class InMemoryRateLimiter:
    """Sliding-window limiter backed by per-tenant deques of timestamps."""

    def __init__(self, *, time_fn=time.monotonic) -> None:
        self._time = time_fn
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(
        self, tenant_id: str, per_minute: int, per_hour: int
    ) -> None:
        """Record a request and raise if either window is over quota.

        The call is accepted *before* checking: the new timestamp is
        appended, then the windows are counted. If the appended point
        pushes us over, we roll back and raise. This keeps the sliding
        window consistent with "check at start of turn" semantics.
        """
        now = float(self._time())
        async with self._lock:
            q = self._events[tenant_id]
            cutoff = now - _HOUR
            while q and q[0] < cutoff:
                q.popleft()

            minute_cutoff = now - _MINUTE
            # Count how many fall within the minute window.
            minute_count = 0
            for ts in reversed(q):
                if ts >= minute_cutoff:
                    minute_count += 1
                else:
                    break

            if len(q) + 1 > per_hour:
                raise RateLimitExceededError(tenant_id, "hour")
            if minute_count + 1 > per_minute:
                raise RateLimitExceededError(tenant_id, "minute")

            q.append(now)

    def reset(self, tenant_id: str | None = None) -> None:
        """Test helper — drop history for one tenant or all."""
        if tenant_id is None:
            self._events.clear()
        else:
            self._events.pop(tenant_id, None)


__all__ = [
    "InMemoryRateLimiter",
    "RateLimitExceededError",
    "RateLimiter",
]
