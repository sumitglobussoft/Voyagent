"""Pytest fixtures for real-Postgres integration tests.

These tests are OPT-IN. They only run when ``VOYAGENT_TEST_DB_URL`` is
set to a reachable Postgres DSN (e.g.
``postgresql+asyncpg://voyagent_test:password@127.0.0.1:5432/voyagent_test``).
If the env var is unset the whole module is skipped at collection time —
so ``uv run pytest`` never fails just because a developer doesn't have
Postgres running locally.

The rest of the suite uses ``sqlite+aiosqlite`` which is plenty fast but
misses Postgres-specific behavior (JSONB typing, server-side enum
constraints, ``ON CONFLICT`` semantics, FK cascade ordering). This
fixture exists so a single end-to-end flow can exercise those against a
real PG instance — either locally or in a scheduled CI job.

Schema bootstrap strategy:
    We try ``alembic upgrade head`` first (preferred — that's what
    production uses). If the project does not yet ship an Alembic
    config, we fall back to ``Base.metadata.create_all`` — same
    approach as the unit suite — so the tests still run. Teardown
    truncates every table rather than dropping them, which is faster
    and safer against parallel runs.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import pytest

# Collection-time skip: do this at import time so the test file never
# gets introspected when the env var is unset. Using pytest.skip with
# allow_module_level=True is the idiomatic way to drop a whole module
# during collection.
_TEST_DB_URL = os.environ.get("VOYAGENT_TEST_DB_URL")
if not _TEST_DB_URL:
    pytest.skip(
        "VOYAGENT_TEST_DB_URL is not set — integration tests are opt-in.",
        allow_module_level=True,
    )


# Imports that depend on project code are intentionally below the skip
# so they are never executed in the default `pytest` run.
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

# Auth secret must be set before importing voyagent_api.
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "integration-test-secret-32+bytes-long-value!"
)
os.environ.setdefault("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "true")

from schemas.storage import Base  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Engine / schema                                                             #
# --------------------------------------------------------------------------- #


def _run_alembic_upgrade(url: str) -> bool:
    """Try to run ``alembic upgrade head`` against ``url``.

    Returns True on success, False if Alembic is not configured in this
    repo (the fallback path is metadata.create_all).
    """
    try:
        from alembic import command  # type: ignore[import-not-found]
        from alembic.config import Config  # type: ignore[import-not-found]
    except Exception:
        return False

    # Look for an alembic.ini next to the API service.
    candidates = [
        os.path.join("services", "api", "alembic.ini"),
        "alembic.ini",
    ]
    ini = next((p for p in candidates if os.path.isfile(p)), None)
    if ini is None:
        return False

    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return True


@pytest.fixture(scope="session")
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped engine bound to ``VOYAGENT_TEST_DB_URL``.

    Runs Alembic (or ``create_all`` as a fallback) to set up the schema
    and truncates every table on teardown.
    """
    assert _TEST_DB_URL is not None  # narrowed by module-level skip
    engine = create_async_engine(_TEST_DB_URL, future=True, pool_pre_ping=True)

    used_alembic = _run_alembic_upgrade(_TEST_DB_URL)
    if not used_alembic:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        # Truncate every table. ``RESTART IDENTITY CASCADE`` lets us
        # wipe in one statement without worrying about FK order.
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema()"
                )
            )
            tables = [row[0] for row in result.fetchall()]
            if tables:
                quoted = ", ".join(f'"{t}"' for t in tables)
                await conn.execute(
                    text(
                        f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"
                    )
                )
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _install_engine(
    pg_engine: AsyncEngine,
) -> AsyncIterator[None]:
    """Install the Postgres engine into the API process for each test."""
    sm = async_sessionmaker(bind=pg_engine, expire_on_commit=False)
    db_module.set_engine_for_test(pg_engine, sm)
    try:
        yield
    finally:
        db_module.set_engine_for_test(None)


# --------------------------------------------------------------------------- #
# HTTP client + fresh user                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def authed_client(client: TestClient) -> tuple[TestClient, dict]:
    """Sign up a brand-new user and return a client with auth headers.

    The returned dict contains ``access_token``, ``refresh_token``,
    ``user``, and the original sign-up credentials so tests can also
    reuse them for a UI-level sign-in if they want.
    """
    import uuid

    suffix = uuid.uuid4().hex[:10]
    body = {
        "email": f"integration-{suffix}@mailinator.com",
        "password": "IntegrationTest123!",
        "full_name": "Integration Tester",
        "agency_name": f"Integration Agency {suffix}",
    }
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    client.headers.update(
        {"Authorization": f"Bearer {payload['access_token']}"}
    )
    return client, {**payload, "credentials": body}
