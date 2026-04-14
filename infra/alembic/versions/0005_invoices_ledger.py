"""invoices, bills, ledger_accounts, journal_entries

Revision ID: 0005_invoices_ledger
Revises: 0004_approval_ttl
Create Date: 2026-04-14

Adds the finance document layer (invoices + bills) and the double-entry
ledger layer (ledger_accounts + journal_entries). The document tables
back the ``/reports/receivables`` and ``/reports/payables`` aging
endpoints; the ledger tables exist so that trial-balance / GL reports
can land in a later revision without further schema churn.

The ``down_revision`` references ``0004_approval_ttl`` which is authored
by a parallel agent — Alembic resolves the chain at ``upgrade head``
time, so nothing more is needed here.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_invoices_ledger"
down_revision: str | None = "0004_approval_ttl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INVOICE_STATUS_VALUES = (
    "draft",
    "issued",
    "partially_paid",
    "paid",
    "void",
)
_BILL_STATUS_VALUES = (
    "draft",
    "received",
    "scheduled",
    "paid",
    "void",
)
_LEDGER_ACCOUNT_TYPE_VALUES = (
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
)


def _pg_enum(name: str, values: Sequence[str]) -> postgresql.ENUM:
    # ``create_type=False`` — we explicitly create the type below once.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ----- Postgres enum types (noop on SQLite) ------------------------- #
    if is_pg:
        postgresql.ENUM(
            *_INVOICE_STATUS_VALUES, name="invoice_status"
        ).create(bind, checkfirst=True)
        postgresql.ENUM(
            *_BILL_STATUS_VALUES, name="bill_status"
        ).create(bind, checkfirst=True)
        postgresql.ENUM(
            *_LEDGER_ACCOUNT_TYPE_VALUES, name="ledger_account_type"
        ).create(bind, checkfirst=True)

    invoice_status_type: sa.types.TypeEngine
    bill_status_type: sa.types.TypeEngine
    ledger_account_type_type: sa.types.TypeEngine
    if is_pg:
        invoice_status_type = _pg_enum("invoice_status", _INVOICE_STATUS_VALUES)
        bill_status_type = _pg_enum("bill_status", _BILL_STATUS_VALUES)
        ledger_account_type_type = _pg_enum(
            "ledger_account_type", _LEDGER_ACCOUNT_TYPE_VALUES
        )
    else:
        invoice_status_type = sa.Enum(
            *_INVOICE_STATUS_VALUES, name="invoice_status"
        )
        bill_status_type = sa.Enum(*_BILL_STATUS_VALUES, name="bill_status")
        ledger_account_type_type = sa.Enum(
            *_LEDGER_ACCOUNT_TYPE_VALUES, name="ledger_account_type"
        )

    # ----- invoices ----------------------------------------------------- #
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("party_name", sa.String(length=255), nullable=False),
        sa.Column("party_reference", sa.String(length=128), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "amount_paid",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            invoice_status_type,
            nullable=False,
            server_default="draft",
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
        sa.UniqueConstraint(
            "tenant_id", "number", name="ux_invoices_tenant_number"
        ),
    )
    op.create_index(
        "ix_invoices_tenant_id", "invoices", ["tenant_id"]
    )
    op.create_index(
        "ix_invoices_tenant_status_due",
        "invoices",
        ["tenant_id", "status", "due_date"],
    )
    op.create_index(
        "ix_invoices_tenant_issue",
        "invoices",
        ["tenant_id", "issue_date"],
    )

    # ----- bills -------------------------------------------------------- #
    op.create_table(
        "bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("vendor_reference", sa.String(length=128), nullable=False),
        sa.Column("party_name", sa.String(length=255), nullable=False),
        sa.Column("party_reference", sa.String(length=128), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "amount_paid",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            bill_status_type,
            nullable=False,
            server_default="draft",
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
        sa.UniqueConstraint(
            "tenant_id",
            "vendor_reference",
            name="ux_bills_tenant_vendor_reference",
        ),
    )
    op.create_index("ix_bills_tenant_id", "bills", ["tenant_id"])
    op.create_index(
        "ix_bills_tenant_status_due",
        "bills",
        ["tenant_id", "status", "due_date"],
    )
    op.create_index(
        "ix_bills_tenant_issue",
        "bills",
        ["tenant_id", "issue_date"],
    )

    # ----- ledger_accounts --------------------------------------------- #
    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", ledger_account_type_type, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint(
            "tenant_id", "code", name="ux_ledger_accounts_tenant_code"
        ),
    )
    op.create_index(
        "ix_ledger_accounts_tenant_id",
        "ledger_accounts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ledger_accounts_tenant_active",
        "ledger_accounts",
        ["tenant_id", "is_active"],
    )

    # ----- journal_entries --------------------------------------------- #
    op.create_table(
        "journal_entries",
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "debit",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "credit",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column(
            "posted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint(
            "entry_id", "line_no", name="pk_journal_entries"
        ),
    )
    op.create_index(
        "ix_journal_entries_tenant_id",
        "journal_entries",
        ["tenant_id"],
    )
    op.create_index(
        "ix_journal_entries_account_id",
        "journal_entries",
        ["account_id"],
    )
    op.create_index(
        "ix_journal_entries_tenant_posted",
        "journal_entries",
        ["tenant_id", "posted_at"],
    )
    op.create_index(
        "ix_journal_entries_entry",
        "journal_entries",
        ["entry_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_journal_entries_entry", table_name="journal_entries"
    )
    op.drop_index(
        "ix_journal_entries_tenant_posted", table_name="journal_entries"
    )
    op.drop_index(
        "ix_journal_entries_account_id", table_name="journal_entries"
    )
    op.drop_index(
        "ix_journal_entries_tenant_id", table_name="journal_entries"
    )
    op.drop_table("journal_entries")

    op.drop_index(
        "ix_ledger_accounts_tenant_active", table_name="ledger_accounts"
    )
    op.drop_index(
        "ix_ledger_accounts_tenant_id", table_name="ledger_accounts"
    )
    op.drop_table("ledger_accounts")

    op.drop_index("ix_bills_tenant_issue", table_name="bills")
    op.drop_index("ix_bills_tenant_status_due", table_name="bills")
    op.drop_index("ix_bills_tenant_id", table_name="bills")
    op.drop_table("bills")

    op.drop_index("ix_invoices_tenant_issue", table_name="invoices")
    op.drop_index("ix_invoices_tenant_status_due", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id", table_name="invoices")
    op.drop_table("invoices")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(name="ledger_account_type").drop(bind, checkfirst=True)
        postgresql.ENUM(name="bill_status").drop(bind, checkfirst=True)
        postgresql.ENUM(name="invoice_status").drop(bind, checkfirst=True)
