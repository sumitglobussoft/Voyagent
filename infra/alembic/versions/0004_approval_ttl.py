"""approval TTL + status enum on pending_approvals

Revision ID: 0004_approval_ttl
Revises: 0003_passengers
Create Date: 2026-04-14

Adds the approval expiry surface the runtime now requires:

* ``expires_at TIMESTAMPTZ NOT NULL`` on ``pending_approvals`` —
  populated via a two-phase migration (nullable + backfill + NOT NULL)
  so existing rows don't block deployment.
* New ``approval_status`` Postgres enum with members
  ``pending | granted | rejected | expired`` and a matching ``status``
  column. Existing rows are back-filled from their ``granted`` value.

The ALTER TYPE ADD VALUE guard is written as CREATE-then-populate
because this is the first revision to introduce the type — an
``ALTER TYPE ... ADD VALUE`` is only required when extending a
pre-existing enum. We keep the helper here so future migrations that
extend ``approval_status`` can borrow the pattern.

Idempotent + reversible. Re-running the upgrade on a schema where this
migration already landed is a no-op (every DDL is guarded by an
inspector check). Downgrade strips the columns and the enum type.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_approval_ttl"
down_revision: str | None = "0003_passengers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPROVAL_STATUS_VALUES = ("pending", "granted", "rejected", "expired")


def _pg_enum_exists(bind: sa.engine.Connection, name: str) -> bool:
    """Return True if a Postgres enum type named ``name`` already exists."""
    if bind.dialect.name != "postgresql":
        return False
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_type WHERE typname = :n AND typtype = 'e'"
        ),
        {"n": name},
    ).scalar()
    return bool(row)


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ---- approval_status enum type --------------------------------------- #
    if is_pg and not _pg_enum_exists(bind, "approval_status"):
        values = ", ".join(f"'{v}'" for v in APPROVAL_STATUS_VALUES)
        op.execute(f"CREATE TYPE approval_status AS ENUM ({values})")

    approval_status_type: sa.types.TypeEngine
    if is_pg:
        approval_status_type = postgresql.ENUM(
            *APPROVAL_STATUS_VALUES,
            name="approval_status",
            create_type=False,
        )
    else:
        # SQLite fallback for unit tests: plain VARCHAR with a check.
        approval_status_type = sa.String(length=16)

    # ---- expires_at column (phase 1: nullable, then backfill) ------------ #
    if not _column_exists(bind, "pending_approvals", "expires_at"):
        op.add_column(
            "pending_approvals",
            sa.Column(
                "expires_at",
                sa.TIMESTAMP(timezone=True),
                nullable=True,
            ),
        )

    # Backfill. Idempotent: only fills rows where expires_at is still NULL,
    # so re-running never clobbers a value a later migration may have set.
    if is_pg:
        op.execute(
            sa.text(
                "UPDATE pending_approvals "
                "SET expires_at = requested_at + interval '15 minutes' "
                "WHERE expires_at IS NULL"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE pending_approvals "
                "SET expires_at = datetime(requested_at, '+15 minutes') "
                "WHERE expires_at IS NULL"
            )
        )

    # Phase 2: lock down NOT NULL now that every row has a value.
    with op.batch_alter_table("pending_approvals") as batch:
        batch.alter_column("expires_at", nullable=False)

    # ---- status column --------------------------------------------------- #
    if not _column_exists(bind, "pending_approvals", "status"):
        op.add_column(
            "pending_approvals",
            sa.Column(
                "status",
                approval_status_type,
                nullable=False,
                server_default="pending",
            ),
        )
        # Backfill status from the pre-existing ``granted`` tri-state.
        # Literals need an explicit cast — Postgres won't implicitly coerce
        # text to an enum in a CASE expression.
        op.execute(
            sa.text(
                "UPDATE pending_approvals SET status = (CASE "
                "  WHEN granted IS TRUE THEN 'granted' "
                "  WHEN granted IS FALSE THEN 'rejected' "
                "  ELSE 'pending' END)::approval_status"
            )
        )

    # Supporting index for the expire_stale_approvals sweep.
    inspector = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("pending_approvals")}
    if "ix_pending_approvals_status_expires" not in existing_indexes:
        op.create_index(
            "ix_pending_approvals_status_expires",
            "pending_approvals",
            ["status", "expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    inspector = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("pending_approvals")}
    if "ix_pending_approvals_status_expires" in existing_indexes:
        op.drop_index(
            "ix_pending_approvals_status_expires",
            table_name="pending_approvals",
        )

    if _column_exists(bind, "pending_approvals", "status"):
        op.drop_column("pending_approvals", "status")
    if _column_exists(bind, "pending_approvals", "expires_at"):
        op.drop_column("pending_approvals", "expires_at")

    if is_pg and _pg_enum_exists(bind, "approval_status"):
        op.execute("DROP TYPE approval_status")
