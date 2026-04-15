"""totp columns + api_keys table

Revision ID: 0010_totp_and_api_keys
Revises: 0009_invoice_draft_status
Create Date: 2026-04-14

Adds the ``users.totp_secret`` + ``users.totp_enabled`` columns for
TOTP 2FA and creates the ``api_keys`` table for headless access.

The TOTP secret is stored as base32 plaintext for v0 — a follow-up
migration will wrap it in :class:`schemas.storage.crypto.FernetEnvKMS`
once the envelope scheme is agreed.

The ``api_keys`` table has an index on ``prefix`` so the bearer-token
lookup path is O(1) — the prefix is the first 8 urlsafe chars of the
key, displayed in the UI and carried in the ``Authorization`` header.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_totp_and_api_keys"
# Chains directly onto 0008_invites. The 0009_invoice_draft_status slot
# is owned by the agent-to-ledger pack and lands separately; alembic
# cares about the chain not the revision-id ordering.
down_revision: str | None = "0008_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users TOTP columns ---------------------------------------- #
    op.add_column(
        "users",
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- api_keys table -------------------------------------------- #
    op.create_table(
        "api_keys",
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
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "scopes",
            sa.String(length=255),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "expires_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "revoked_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "last_used_at", sa.TIMESTAMP(timezone=True), nullable=True
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
        sa.UniqueConstraint("key_hash", name="ux_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index(
        "ix_api_keys_created_by_user_id",
        "api_keys",
        ["created_by_user_id"],
    )
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index(
        "ix_api_keys_tenant_revoked",
        "api_keys",
        ["tenant_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_tenant_revoked", table_name="api_keys")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index(
        "ix_api_keys_created_by_user_id", table_name="api_keys"
    )
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
