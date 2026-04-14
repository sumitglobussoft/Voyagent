"""API-side audit sink + auth-failure recording helpers.

The agent runtime owns a rich :class:`AuditSink` protocol — we reuse
the canonical :class:`AuditEvent` shape here so auth-failure rows land
in the same table as tool invocations. When the runtime module is not
importable (e.g. bare-API deploys) we fall back to an in-memory list
keyed on the process so ``/auth/verify`` rejections still surface in
tests and local dev.

Rate limiting
-------------
A broken client with a stale token will pound ``/chat/*`` hundreds of
times a minute. :func:`record_auth_failure` caps writes at 5 per
minute per ``(remote_addr, path)`` so the audit table doesn't drown.
The limiter uses Redis when available, in-process LRU otherwise.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Sink shim                                                                   #
# --------------------------------------------------------------------------- #


class _ApiAuditSinkShim(Protocol):
    async def write(self, event: Any) -> None: ...


class _InMemoryApiAuditSink:
    """Trivial in-memory sink for dev + tests."""

    def __init__(self) -> None:
        self._events: list[Any] = []

    async def write(self, event: Any) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Any]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


_api_sink: _ApiAuditSinkShim | None = None


def get_api_audit_sink() -> _ApiAuditSinkShim:
    """Return the process-wide API audit sink.

    Prefers the runtime's configured sink when both services are
    co-located; falls back to the in-memory shim.
    """
    global _api_sink
    if _api_sink is not None:
        return _api_sink
    try:
        # Build a runtime bundle only if one has already been built by
        # the chat layer. We avoid forcing the agent runtime to boot
        # solely to record auth failures.
        from voyagent_api import chat as _chat  # noqa: WPS433

        bundle = _chat._bundle  # type: ignore[attr-defined]
        if bundle is not None and getattr(bundle, "audit_sink", None) is not None:
            _api_sink = bundle.audit_sink
            return _api_sink
    except Exception:  # noqa: BLE001
        pass
    _api_sink = _InMemoryApiAuditSink()
    return _api_sink


def set_api_audit_sink_for_test(sink: _ApiAuditSinkShim | None) -> None:
    global _api_sink
    _api_sink = sink


# --------------------------------------------------------------------------- #
# Rate limiter                                                                #
# --------------------------------------------------------------------------- #


_INMEM_LIMITER: OrderedDict[str, tuple[int, int]] = OrderedDict()
_INMEM_LIMIT_CAP = 2048  # evict oldest entries past this soft cap
_RATE_LIMIT = 5
_RATE_WINDOW_SECONDS = 60


def _allow_inmem(key: str) -> bool:
    """In-memory token-bucket sibling to the Redis limiter."""
    now = int(time.time())
    bucket = _INMEM_LIMITER.get(key)
    if bucket is None or bucket[1] + _RATE_WINDOW_SECONDS <= now:
        _INMEM_LIMITER[key] = (1, now)
        _INMEM_LIMITER.move_to_end(key)
        while len(_INMEM_LIMITER) > _INMEM_LIMIT_CAP:
            _INMEM_LIMITER.popitem(last=False)
        return True
    count, first_ts = bucket
    if count >= _RATE_LIMIT:
        return False
    _INMEM_LIMITER[key] = (count + 1, first_ts)
    _INMEM_LIMITER.move_to_end(key)
    return True


async def _allow_redis(key: str) -> bool | None:
    """Return ``True``/``False`` on Redis path, or ``None`` on failure."""
    url = os.environ.get("VOYAGENT_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    try:
        client = redis_async.from_url(url, decode_responses=True)
        rkey = f"voyagent:auth_fail:{key}"
        count = await client.incr(rkey)
        if int(count) == 1:
            await client.expire(rkey, _RATE_WINDOW_SECONDS)
        return int(count) <= _RATE_LIMIT
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure rate-limit Redis path failed: %s", exc)
        return None


async def _allow(remote_addr: str, path: str) -> bool:
    key = f"{remote_addr}|{path}"
    verdict = await _allow_redis(key)
    if verdict is not None:
        return verdict
    return _allow_inmem(key)


# --------------------------------------------------------------------------- #
# Record                                                                      #
# --------------------------------------------------------------------------- #


_SYSTEM_TENANT_ID = "00000000-0000-7000-8000-000000000000"
"""Synthetic "system" tenant id used when the real one is unknown.

Matches the UUIDv7 pattern the canonical ``EntityId`` regex accepts.
When the storage layer enforces a real FK on ``tenant_id`` this id
will need a seed row — v0 uses the in-memory audit sink path which
carries no FK.
"""


async def record_auth_failure(
    *,
    error_code: str,
    method: str,
    path: str,
    remote_addr: str,
    tenant_id: str | None = None,
) -> None:
    """Append an auth-failure :class:`AuditEvent` — best-effort.

    Rate-limited to 5 events / minute / ``(remote_addr, path)`` so a
    broken client does not flood the audit log.
    """
    if not await _allow(remote_addr, path):
        return

    try:
        from schemas.canonical import ActorKind, AuditEvent, AuditStatus
    except Exception as exc:  # noqa: BLE001
        logger.debug("canonical audit types unavailable: %s", exc)
        return

    now = datetime.now(timezone.utc)
    try:
        event = AuditEvent(
            id=_uuid7_like(),
            tenant_id=tenant_id or _SYSTEM_TENANT_ID,
            actor_id=_SYSTEM_TENANT_ID,
            actor_kind=ActorKind.SYSTEM,
            tool="auth.verify",
            inputs={"method": method, "path": path, "remote_addr": remote_addr},
            started_at=now,
            completed_at=now,
            status=AuditStatus.REJECTED,
            error=error_code,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure AuditEvent build failed: %s", exc)
        return

    sink = get_api_audit_sink()
    try:
        await sink.write(event)
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure sink.write failed: %s", exc)


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


__all__ = [
    "get_api_audit_sink",
    "record_auth_failure",
    "set_api_audit_sink_for_test",
]
