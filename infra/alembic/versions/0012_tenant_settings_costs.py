"""tenant_settings + session_costs tables

Revision ID: 0012_tenant_settings_costs
Revises: 0011_approvals_payload
Create Date: 2026-04-14

Adds per-tenant runtime settings (model override, prompt suffix, rate
limits, locale/timezone/currency) and the per-turn cost ledger used by
the daily-budget enforcement path.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_tenant_settings_costs"
down_revision: str | None = "0011_approvals_payload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("system_prompt_suffix", sa.Text(), nullable=True),
        sa.Column(
            "rate_limit_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column(
            "rate_limit_per_hour",
            sa.Integer(),
            nullable=False,
            server_default="1000",
        ),
        sa.Column("daily_token_budget", sa.Integer(), nullable=True),
        sa.Column(
            "locale",
            sa.String(length=16),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column(
            "default_currency",
            sa.String(length=3),
            nullable=False,
            server_default="INR",
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
        sa.CheckConstraint(
            "length(default_currency) = 3",
            name="ck_tenant_settings_currency_len",
        ),
        sa.CheckConstraint(
            "rate_limit_per_minute > 0",
            name="ck_tenant_settings_rpm_pos",
        ),
        sa.CheckConstraint(
            "rate_limit_per_hour > 0",
            name="ck_tenant_settings_rph_pos",
        ),
    )

    op.create_table(
        "session_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(14, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_session_costs_tenant_created",
        "session_costs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_session_costs_session_id",
        "session_costs",
        ["session_id"],
    )
    op.create_index(
        "ix_session_costs_tenant_id",
        "session_costs",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_costs_tenant_id", table_name="session_costs")
    op.drop_index("ix_session_costs_session_id", table_name="session_costs")
    op.drop_index(
        "ix_session_costs_tenant_created", table_name="session_costs"
    )
    op.drop_table("session_costs")
    op.drop_table("tenant_settings")
