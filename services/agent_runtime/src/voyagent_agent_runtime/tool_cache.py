"""TTL cache for idempotent tool reads.

Scoped by ``(tenant_id, tool_name, input_hash)`` — never shared across
tenants. Only cacheable tools on the explicit allowlist hit the cache;
side-effect tools bypass it entirely.

The cache is a plain in-memory dict with wall-clock TTLs. Multi-process
deployments that need coherence between replicas should front this
with Redis, but for v0 a process-local cache is enough: the worst case
on a miss is an extra upstream call, not a correctness bug.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Explicit allowlist of read-only tools that may be served from cache.
# Write-side tools (book, issue_ticket, post_journal_entry, draft_invoice)
# are intentionally absent and will never be cached.
CACHEABLE_TOOLS: frozenset[str] = frozenset(
    {
        "search_flights",
        "search_hotels",
        "check_hotel_rate",
        "list_ledger_accounts",
        "lookup_passenger",
    }
)

DEFAULT_TTL_SECONDS: float = 300.0  # 5 minutes
"""Default cache TTL. Per-tool overrides live in :data:`PER_TOOL_TTL`."""

PER_TOOL_TTL: dict[str, float] = {
    # Rates move faster than directory data — shorter cache.
    "check_hotel_rate": 120.0,
    "list_ledger_accounts": 600.0,
}


def _hash_input(tool_input: dict[str, Any]) -> str:
    """Stable hash of a tool input dict. Sort keys so order never matters."""
    payload = json.dumps(tool_input, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    value: dict[str, Any]
    expires_at: float


class ToolResultCache:
    """Per-tenant TTL cache for idempotent tool outputs."""

    def __init__(
        self,
        *,
        default_ttl: float = DEFAULT_TTL_SECONDS,
        time_fn=time.monotonic,
    ) -> None:
        self._default_ttl = float(default_ttl)
        self._time = time_fn
        self._store: dict[tuple[str, str, str], _Entry] = {}
        self._lock = asyncio.Lock()
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def is_cacheable(tool_name: str) -> bool:
        return tool_name in CACHEABLE_TOOLS

    def ttl_for(self, tool_name: str) -> float:
        return PER_TOOL_TTL.get(tool_name, self._default_ttl)

    async def get(
        self, tenant_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not self.is_cacheable(tool_name):
            return None
        key = (tenant_id, tool_name, _hash_input(tool_input))
        now = float(self._time())
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= now:
                # Expired — drop it and treat as miss.
                self._store.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            logger.debug(
                "tool_cache.hit tenant=%s tool=%s", tenant_id, tool_name
            )
            return dict(entry.value)

    async def put(
        self,
        tenant_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        value: dict[str, Any],
    ) -> None:
        if not self.is_cacheable(tool_name):
            return
        key = (tenant_id, tool_name, _hash_input(tool_input))
        ttl = self.ttl_for(tool_name)
        async with self._lock:
            self._store[key] = _Entry(
                value=dict(value),
                expires_at=float(self._time()) + ttl,
            )

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._store),
        }

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0


__all__ = [
    "CACHEABLE_TOOLS",
    "DEFAULT_TTL_SECONDS",
    "PER_TOOL_TTL",
    "ToolResultCache",
]
