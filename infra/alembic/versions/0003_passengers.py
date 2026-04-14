"""passengers: tenant-scoped traveler identity table

Revision ID: 0003_passengers
Revises: 0002_inhouse_auth
Create Date: 2026-04-14

Adds the ``passengers`` table that backs
:class:`voyagent_agent_runtime.passenger_resolver.StoragePassengerResolver`.
The runtime previously carried an in-memory resolver only; this revision
is the storage surface that lets the Postgres-backed resolver persist
travelers across turns and processes.

Designed to be idempotent — the create-table and index creation are
guarded with ``IF NOT EXISTS`` via ``checkfirst`` so re-running the
migration in environments where an earlier manual create landed first
will not error.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_passengers"
down_revision: str | None = "0002_inhouse_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "passengers" not in existing_tables:
        op.create_table(
            "passengers",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("phone", sa.String(length=32), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("passport_number", sa.String(length=64), nullable=True),
            sa.Column("passport_expiry", sa.Date(), nullable=True),
            sa.Column("nationality", sa.String(length=2), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("passengers")}

    if "ix_passengers_tenant_id" not in existing_indexes:
        op.create_index(
            "ix_passengers_tenant_id",
            "passengers",
            ["tenant_id"],
        )
    if "ux_passengers_tenant_email" not in existing_indexes:
        op.create_index(
            "ux_passengers_tenant_email",
            "passengers",
            ["tenant_id", "email"],
            unique=True,
        )
    if "ux_passengers_tenant_passport" not in existing_indexes:
        op.create_index(
            "ux_passengers_tenant_passport",
            "passengers",
            ["tenant_id", "passport_number"],
            unique=True,
        )
    if "ix_passengers_tenant_created" not in existing_indexes:
        op.create_index(
            "ix_passengers_tenant_created",
            "passengers",
            ["tenant_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_passengers_tenant_created", table_name="passengers")
    op.drop_index("ux_passengers_tenant_passport", table_name="passengers")
    op.drop_index("ux_passengers_tenant_email", table_name="passengers")
    op.drop_index("ix_passengers_tenant_id", table_name="passengers")
    op.drop_table("passengers")
