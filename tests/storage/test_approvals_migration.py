"""Verify migration 0011 adds payload + resolved_by_user_id to pending_approvals.

Unit tests do not spin up the full alembic runner (that lives behind
an integration marker and targets Postgres). Instead we assert two
independent things:

1. The alembic revision file exists and declares the expected chain
   (``down_revision = "0010_totp_and_api_keys"``) plus both columns.
2. The ORM :class:`PendingApprovalRow` carries the two columns, so
   ``Base.metadata.create_all`` in SQLite tests produces a table that
   the /approvals HTTP surface can read + write against. If the ORM
   drifts from the migration this test yells.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine
import pytest

from schemas.storage import Base
from schemas.storage.session import PendingApprovalRow


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "infra"
    / "alembic"
    / "versions"
    / "0011_approvals_payload.py"
)


def test_migration_file_present_and_chained() -> None:
    assert _MIGRATION_PATH.exists(), (
        f"expected migration at {_MIGRATION_PATH}"
    )
    text = _MIGRATION_PATH.read_text()
    assert 'revision: str = "0011_approvals_payload"' in text
    assert 'down_revision: str | None = "0010_totp_and_api_keys"' in text
    # Both columns show up in the upgrade body.
    assert '"payload"' in text
    assert '"resolved_by_user_id"' in text
    assert "add_column" in text


def test_orm_row_declares_new_columns() -> None:
    columns = {c.name for c in PendingApprovalRow.__table__.columns}
    assert "payload" in columns
    assert "resolved_by_user_id" in columns


@pytest.mark.asyncio
async def test_create_all_produces_columns_on_sqlite() -> None:
    """End-to-end check: ``Base.metadata.create_all`` creates the
    ``pending_approvals`` table with the two new columns. This is the
    exact path the API tests use, so if this passes they will too."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def _inspect(sync_conn):
                insp = sa_inspect(sync_conn)
                return {
                    c["name"]
                    for c in insp.get_columns("pending_approvals")
                }

            columns = await conn.run_sync(_inspect)
    finally:
        await engine.dispose()

    assert "payload" in columns
    assert "resolved_by_user_id" in columns
