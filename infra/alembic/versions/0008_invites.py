"""team invites table

Revision ID: 0008_invites
Revises: 0007_session_title
Create Date: 2026-04-14

Creates the ``invites`` table + ``invite_status`` enum. Invites let
an agency_admin add teammates into an existing tenant without the
sign-up path (which mints a fresh tenant). Token itself is never
stored — only the sha256 hex digest. A partial-free unique index over
``(tenant_id, lower(email))`` dedupes invites per tenant.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_invites"
down_revision: str | None = "0007_session_title"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INVITE_STATUS_VALUES = ("pending", "accepted", "revoked", "expired")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        invite_status = postgresql.ENUM(
            *_INVITE_STATUS_VALUES, name="invite_status", create_type=False
        )
        invite_status.create(bind, checkfirst=True)
        status_col_type: sa.types.TypeEngine = invite_status
    else:
        status_col_type = sa.String(length=16)

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="agent",
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            status_col_type,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "accepted_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "revoked_at", sa.TIMESTAMP(timezone=True), nullable=True
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
        sa.UniqueConstraint("token_hash", name="ux_invites_token_hash"),
    )
    op.create_index("ix_invites_tenant_id", "invites", ["tenant_id"])
    op.create_index(
        "ix_invites_invited_by_user_id", "invites", ["invited_by_user_id"]
    )
    op.create_index(
        "ix_invites_tenant_status", "invites", ["tenant_id", "status"]
    )
    op.create_index(
        "ux_invites_tenant_email_lower",
        "invites",
        ["tenant_id", sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_invites_tenant_email_lower", table_name="invites")
    op.drop_index("ix_invites_tenant_status", table_name="invites")
    op.drop_index("ix_invites_invited_by_user_id", table_name="invites")
    op.drop_index("ix_invites_tenant_id", table_name="invites")
    op.drop_table("invites")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(
            *_INVITE_STATUS_VALUES, name="invite_status"
        ).drop(bind, checkfirst=True)
