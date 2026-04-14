"""Email-verification token storage for the in-house auth service.

Parallels :mod:`voyagent_api.revocation`: a thin protocol with an
in-memory implementation for dev/tests and a Redis implementation for
production. Tokens are short-lived (default 24 h) and are keyed to the
user they verify.

The actual email delivery is out of scope for this module — the route
layer logs the verification link to stdout and leaves real SMTP /
provider integration as a TODO.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


_REDIS_KEY_PREFIX = "voyagent:email_verify:"


def get_verification_ttl_seconds() -> int:
    """Read ``VOYAGENT_AUTH_VERIFICATION_TTL_SECONDS`` (default 24 h)."""
    raw = os.environ.get("VOYAGENT_AUTH_VERIFICATION_TTL_SECONDS", "").strip()
    if not raw:
        return 24 * 3600
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid VOYAGENT_AUTH_VERIFICATION_TTL_SECONDS=%r; using 24h", raw
        )
        return 24 * 3600
    return max(60, value)


@runtime_checkable
class VerificationTokenStore(Protocol):
    """Minimal KV surface for verification tokens."""

    async def put(self, token: str, user_id: str, ttl_seconds: int) -> None: ...

    async def take(self, token: str) -> str | None: ...


class NullVerificationTokenStore:
    """In-memory store. Used in local dev and tests."""

    def __init__(self) -> None:
        # token -> (user_id, expires_at_epoch_seconds)
        self._tokens: dict[str, tuple[str, int]] = {}

    async def put(self, token: str, user_id: str, ttl_seconds: int) -> None:
        self._tokens[token] = (user_id, int(time.time()) + int(ttl_seconds))

    async def take(self, token: str) -> str | None:
        entry = self._tokens.get(token)
        if entry is None:
            return None
        user_id, exp = entry
        if exp <= int(time.time()):
            self._tokens.pop(token, None)
            return None
        self._tokens.pop(token, None)
        return user_id


class RedisVerificationTokenStore:
    """Redis-backed store with per-key TTL.

    Fail-open on reads (miss looks the same as an invalid token), fail-
    loud on writes so ``send-verification-email`` errors reach the
    client.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def put(self, token: str, user_id: str, ttl_seconds: int) -> None:
        await self._client.set(_REDIS_KEY_PREFIX + token, user_id, ex=int(ttl_seconds))

    async def take(self, token: str) -> str | None:
        key = _REDIS_KEY_PREFIX + token
        try:
            value = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("verification-token GET failed: %s", exc)
            return None
        if value is None:
            return None
        try:
            await self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("verification-token DELETE failed: %s", exc)
        return value if isinstance(value, str) else value.decode("utf-8")


_singleton: VerificationTokenStore | None = None


def set_verification_token_store_for_test(
    store: VerificationTokenStore | None,
) -> None:
    """Install a process-wide :class:`VerificationTokenStore` (tests)."""
    global _singleton
    _singleton = store


def build_verification_token_store(
    *, env: dict[str, str] | None = None
) -> VerificationTokenStore:
    """Return the configured :class:`VerificationTokenStore`."""
    global _singleton
    if _singleton is not None:
        return _singleton

    source = env if env is not None else os.environ
    url = source.get("VOYAGENT_REDIS_URL", "").strip()
    if not url:
        _singleton = NullVerificationTokenStore()
        return _singleton

    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "redis.asyncio not installed — falling back to in-memory "
            "verification-token store: %s",
            exc,
        )
        _singleton = NullVerificationTokenStore()
        return _singleton

    try:
        client = redis_async.from_url(url, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "redis.from_url(%s) failed — falling back to in-memory "
            "verification-token store: %s",
            url,
            exc,
        )
        _singleton = NullVerificationTokenStore()
        return _singleton

    _singleton = RedisVerificationTokenStore(client)
    return _singleton


__all__ = [
    "NullVerificationTokenStore",
    "RedisVerificationTokenStore",
    "VerificationTokenStore",
    "build_verification_token_store",
    "get_verification_ttl_seconds",
    "set_verification_token_store_for_test",
]
