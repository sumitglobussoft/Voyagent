"""Alembic environment for the Voyagent storage schema.

Supports both offline (``--sql``) and online modes. Online mode uses
an ``async_engine`` because the production schema expects asyncpg;
Alembic itself runs migrations synchronously inside a ``run_sync``
callback, which is the documented async pattern.

The database URL is read from ``VOYAGENT_DB_URL`` — see
``docs/STACK.md`` for the expected shape
(``postgresql+asyncpg://user:pw@host:5432/voyagent``).
"""

from __future__ import annotations

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import *every* model so ``Base.metadata`` is fully populated before
# Alembic inspects it. A missing import here = a missing table at
# upgrade time, so we import from the package root which re-exports all.
from schemas.storage import Base  # noqa: E402
import schemas.storage  # noqa: F401,E402 — populate metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Prefer ``VOYAGENT_DB_URL``; fall back to ``sqlalchemy.url``.

    The ini file intentionally ships the URL blank; tests that drive
    Alembic programmatically can override via ``config.set_main_option``.
    """
    env_url = os.environ.get("VOYAGENT_DB_URL")
    if env_url:
        return env_url
    ini_url = config.get_main_option("sqlalchemy.url")
    if not ini_url:
        raise RuntimeError(
            "Alembic: no database URL. Set VOYAGENT_DB_URL or "
            "sqlalchemy.url before running migrations."
        )
    return ini_url


# --------------------------------------------------------------------------- #
# Offline mode                                                                #
# --------------------------------------------------------------------------- #


def run_migrations_offline() -> None:
    """Emit SQL scripts without connecting to a database.

    Useful for producing review artefacts (``alembic upgrade head --sql``).
    """
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# --------------------------------------------------------------------------- #
# Online mode                                                                 #
# --------------------------------------------------------------------------- #


def _run_migrations_sync(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect via asyncpg and run migrations inside a sync callback."""
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _resolve_url()

    engine = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
