"""Async SQLAlchemy engine + session factory for the API process.

The agent runtime owns its own engine; the API needs a separate one
because it runs in the FastAPI process and reads/writes auth tables
that are not part of the runtime's surface. We construct a single
engine from ``VOYAGENT_DB_URL`` at first use and cache it for the
lifetime of the process.

Tests override the engine via :func:`set_engine_for_test` so the
in-house auth tests can run against ``sqlite+aiosqlite`` without
touching real Postgres.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_engine_override: AsyncEngine | None = None
_sessionmaker_override: async_sessionmaker[AsyncSession] | None = None


@lru_cache(maxsize=1)
def _default_engine() -> AsyncEngine:
    """Build the process-wide engine from ``VOYAGENT_DB_URL``."""
    url = os.environ.get("VOYAGENT_DB_URL")
    if not url:
        raise RuntimeError(
            "VOYAGENT_DB_URL must be set for the in-house auth service"
        )
    return create_async_engine(url, future=True, pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    """Return the current engine, honoring any test override."""
    if _engine_override is not None:
        return _engine_override
    return _default_engine()


@lru_cache(maxsize=1)
def _default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide sessionmaker."""
    return async_sessionmaker(
        bind=_default_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the active sessionmaker (test override aware)."""
    if _sessionmaker_override is not None:
        return _sessionmaker_override
    return _default_sessionmaker()


def set_engine_for_test(
    engine: AsyncEngine | None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Install a test engine + sessionmaker.

    Pass ``None`` for both to reset back to the production-default
    behavior driven by ``VOYAGENT_DB_URL``.
    """
    global _engine_override, _sessionmaker_override
    _engine_override = engine
    if engine is None:
        _sessionmaker_override = None
    elif sessionmaker is not None:
        _sessionmaker_override = sessionmaker
    else:
        _sessionmaker_override = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )


async def db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a single :class:`AsyncSession`."""
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


__all__ = [
    "db_session",
    "get_engine",
    "get_sessionmaker",
    "set_engine_for_test",
]
