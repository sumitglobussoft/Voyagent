"""inhouse auth: password columns on users + auth_refresh_tokens table

Revision ID: 0002_inhouse_auth
Revises: 0001
Create Date: 2026-04-14

Adds the columns the in-house auth service needs to store credentials
on the existing ``users`` table, swaps the per-tenant email uniqueness
for global email uniqueness (email is the canonical login identifier),
and creates the ``auth_refresh_tokens`` table for hashed refresh-token
storage.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_inhouse_auth"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- users: new auth columns -------------------------------------- #
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # ----- users: swap (tenant_id, email) uniqueness for global email --- #
    # The 0001 migration created ``ux_users_tenant_external`` as a unique
    # index over (tenant_id, external_id). Email uniqueness was only
    # ix_users_email (non-unique). We now want email to be globally
    # unique and external_id to be a non-unique lookup index.
    op.drop_index("ux_users_tenant_external", table_name="users")
    op.create_index(
        "ix_users_tenant_external",
        "users",
        ["tenant_id", "external_id"],
        unique=False,
    )
    op.drop_index("ix_users_email", table_name="users")
    op.create_index(
        "ux_users_email",
        "users",
        ["email"],
        unique=True,
    )

    # ----- auth_refresh_tokens ------------------------------------------ #
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
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
            "token_hash", name="ux_auth_refresh_tokens_token_hash"
        ),
    )
    op.create_index(
        "ix_auth_refresh_tokens_user_id",
        "auth_refresh_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_auth_refresh_tokens_user_expires",
        "auth_refresh_tokens",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_refresh_tokens_user_expires", table_name="auth_refresh_tokens"
    )
    op.drop_index(
        "ix_auth_refresh_tokens_user_id", table_name="auth_refresh_tokens"
    )
    op.drop_table("auth_refresh_tokens")

    op.drop_index("ux_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])
    op.drop_index("ix_users_tenant_external", table_name="users")
    op.create_index(
        "ux_users_tenant_external",
        "users",
        ["tenant_id", "external_id"],
        unique=True,
    )

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "password_hash")
