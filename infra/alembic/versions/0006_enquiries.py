"""enquiries table + enquiry_status enum

Revision ID: 0006_enquiries
Revises: 0005_invoices_ledger
Create Date: 2026-04-14

Adds the ``enquiries`` table backing the agency-side CRUD over customer
travel enquiries (``/api/enquiries/*``). An enquiry is the earliest
pipeline artifact — an agent logs a prospect's intent (route, dates,
pax, budget, notes) and can later promote the row to a chat session
where the agentic runtime plans + prices the trip.

Idempotent + reversible. Re-running the upgrade on a schema where this
migration already landed is a no-op (every DDL is guarded by an
inspector check). Downgrade strips the table, its index, and the enum
type.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_enquiries"
down_revision: str | None = "0005_invoices_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENQUIRY_STATUS_VALUES = ("new", "quoted", "booked", "cancelled")


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


def _table_exists(bind: sa.engine.Connection, name: str) -> bool:
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _index_exists(
    bind: sa.engine.Connection, table: str, index_name: str
) -> bool:
    inspector = sa.inspect(bind)
    if not _table_exists(bind, table):
        return False
    return index_name in {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ----- enquiry_status enum type ------------------------------------- #
    if is_pg and not _pg_enum_exists(bind, "enquiry_status"):
        values = ", ".join(f"'{v}'" for v in ENQUIRY_STATUS_VALUES)
        op.execute(f"CREATE TYPE enquiry_status AS ENUM ({values})")

    enquiry_status_type: sa.types.TypeEngine
    if is_pg:
        enquiry_status_type = postgresql.ENUM(
            *ENQUIRY_STATUS_VALUES,
            name="enquiry_status",
            create_type=False,
        )
    else:
        # SQLite fallback for unit tests: a plain enum without a named type.
        enquiry_status_type = sa.Enum(
            *ENQUIRY_STATUS_VALUES, name="enquiry_status"
        )

    # ----- enquiries table ---------------------------------------------- #
    if not _table_exists(bind, "enquiries"):
        op.create_table(
            "enquiries",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_by_user_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column("customer_name", sa.Text(), nullable=False),
            sa.Column("customer_email", sa.Text(), nullable=True),
            sa.Column("customer_phone", sa.Text(), nullable=True),
            sa.Column("origin", sa.Text(), nullable=True),
            sa.Column("destination", sa.Text(), nullable=True),
            sa.Column("depart_date", sa.Date(), nullable=True),
            sa.Column("return_date", sa.Date(), nullable=True),
            sa.Column(
                "pax_count",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column("budget_amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("budget_currency", sa.CHAR(length=3), nullable=True),
            sa.Column(
                "status",
                enquiry_status_type,
                nullable=False,
                server_default="new",
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "session_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
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

    # Tenant-scoped listing index — fits the default query (tenant-scoped,
    # optional status filter, most-recent-first).
    if not _index_exists(bind, "enquiries", "ix_enquiries_tenant_status_created"):
        op.create_index(
            "ix_enquiries_tenant_status_created",
            "enquiries",
            ["tenant_id", "status", "created_at"],
        )
    # Separate index for audit-by-user queries — kept narrow so it's
    # cheap to maintain on writes.
    if not _index_exists(bind, "enquiries", "ix_enquiries_created_by_user_id"):
        op.create_index(
            "ix_enquiries_created_by_user_id",
            "enquiries",
            ["created_by_user_id"],
        )
    if not _index_exists(bind, "enquiries", "ix_enquiries_tenant_id"):
        op.create_index(
            "ix_enquiries_tenant_id", "enquiries", ["tenant_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if _index_exists(bind, "enquiries", "ix_enquiries_tenant_id"):
        op.drop_index("ix_enquiries_tenant_id", table_name="enquiries")
    if _index_exists(bind, "enquiries", "ix_enquiries_created_by_user_id"):
        op.drop_index(
            "ix_enquiries_created_by_user_id", table_name="enquiries"
        )
    if _index_exists(bind, "enquiries", "ix_enquiries_tenant_status_created"):
        op.drop_index(
            "ix_enquiries_tenant_status_created", table_name="enquiries"
        )

    if _table_exists(bind, "enquiries"):
        op.drop_table("enquiries")

    if is_pg and _pg_enum_exists(bind, "enquiry_status"):
        op.execute("DROP TYPE enquiry_status")
