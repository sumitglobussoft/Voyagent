"""Storage test fixtures.

We use ``aiosqlite`` as the unit-test engine so tests are self-contained
— no Postgres, no network. The schema is created via
``Base.metadata.create_all``, which skips Alembic entirely; that's the
right trade-off for unit tests because the ORM is the source of truth
and a separate migration suite (CI-only) validates the Alembic
revisions against a real Postgres.

Integration tests that must run against Postgres live behind an opt-in
pytest marker so CI can schedule them separately; that wiring is a
future concern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from schemas.storage import Base


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Yield a fresh in-memory SQLite engine with all tables created.

    Each test gets its own engine so state never leaks — in-memory
    SQLite's lifecycle is per-connection, but ``StaticPool`` keeps a
    single connection alive for the engine so multiple queries see the
    same database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()
