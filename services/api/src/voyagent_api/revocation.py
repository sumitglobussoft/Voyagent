"""Token revocation — a JWT denylist keyed on ``jti``.

Background
----------
Voyagent access JWTs are short-lived, but users expect
``/auth/sign-out`` (and admin-driven revocation) to take effect *now*,
not at the next ``exp``. The :class:`RevocationList` protocol provides
the seam; :class:`RedisRevocationList` is the production implementation.

Fail-mode
---------
If Redis is unreachable, :meth:`RedisRevocationList.is_revoked` logs a
WARNING and returns ``False`` — **fail-open**. We prefer availability
over revocation latency: a denylist outage must not 401 every request.
The future ``fail_closed=True`` flag is flagged in the docstring so
high-risk deployments can flip the default.

Keys expire at the token's ``exp``, so the denylist never grows
unboundedly: once the JWT would have expired anyway, the Redis entry
disappears.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


_REDIS_KEY_PREFIX = "voyagent:revoked_jti:"


# --------------------------------------------------------------------------- #
# Protocol                                                                    #
# --------------------------------------------------------------------------- #


@runtime_checkable
class RevocationList(Protocol):
    """Minimal revocation surface used by :mod:`voyagent_api.auth`."""

    async def is_revoked(self, jti: str) -> bool: ...

    async def revoke(self, jti: str, exp_ts: int) -> None: ...


# --------------------------------------------------------------------------- #
# Null implementation                                                         #
# --------------------------------------------------------------------------- #


class NullRevocationList:
    """In-memory set. Used in local dev and tests.

    Not thread-safe in a practical sense because the API process is
    single-threaded async; a worker-per-request deployment must use
    :class:`RedisRevocationList`.
    """

    def __init__(self) -> None:
        self._revoked: dict[str, int] = {}

    async def is_revoked(self, jti: str) -> bool:
        exp = self._revoked.get(jti)
        if exp is None:
            return False
        if exp <= int(time.time()):
            self._revoked.pop(jti, None)
            return False
        return True

    async def revoke(self, jti: str, exp_ts: int) -> None:
        self._revoked[jti] = int(exp_ts)


# --------------------------------------------------------------------------- #
# Redis implementation                                                        #
# --------------------------------------------------------------------------- #


class RedisRevocationList:
    """:class:`RevocationList` backed by Redis string keys with TTL.

    Fail-open by design: Redis errors yield ``is_revoked=False`` so the
    auth layer doesn't 401 everyone during a denylist outage. A
    ``fail_closed=True`` future flag would flip this if the operator
    prefers hardness over availability (noted here rather than built so
    we don't ship untested config).
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def is_revoked(self, jti: str) -> bool:
        key = _REDIS_KEY_PREFIX + jti
        try:
            value = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("revocation list Redis GET failed (fail-open): %s", exc)
            return False
        return value is not None

    async def revoke(self, jti: str, exp_ts: int) -> None:
        key = _REDIS_KEY_PREFIX + jti
        ttl = int(exp_ts) - int(time.time())
        if ttl <= 0:
            # Already expired; nothing to do.
            return
        try:
            await self._client.set(key, "1", ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("revocation list Redis SET failed: %s", exc)


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


_singleton: RevocationList | None = None


def set_revocation_list_for_test(lst: RevocationList | None) -> None:
    """Install a process-wide :class:`RevocationList` (tests)."""
    global _singleton
    _singleton = lst


def build_revocation_list(
    *, env: dict[str, str] | None = None
) -> RevocationList:
    """Return the configured :class:`RevocationList`.

    Uses ``VOYAGENT_REDIS_URL`` if set; falls back to
    :class:`NullRevocationList` otherwise. The return value is cached
    for the lifetime of the process — swap via
    :func:`set_revocation_list_for_test`.
    """
    global _singleton
    if _singleton is not None:
        return _singleton

    source = env if env is not None else os.environ
    url = source.get("VOYAGENT_REDIS_URL", "").strip()
    if not url:
        _singleton = NullRevocationList()
        return _singleton

    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "redis.asyncio not installed — falling back to in-memory "
            "revocation list: %s",
            exc,
        )
        _singleton = NullRevocationList()
        return _singleton

    try:
        client = redis_async.from_url(url, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "redis.from_url(%s) failed — falling back to in-memory "
            "revocation list: %s",
            url,
            exc,
        )
        _singleton = NullRevocationList()
        return _singleton

    _singleton = RedisRevocationList(client)
    return _singleton


__all__ = [
    "NullRevocationList",
    "RedisRevocationList",
    "RevocationList",
    "build_revocation_list",
    "set_revocation_list_for_test",
]
