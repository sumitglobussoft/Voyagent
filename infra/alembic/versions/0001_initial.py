"""initial storage schema: tenants, users, sessions, messages, approvals, audit

Revision ID: 0001
Revises:
Create Date: 2026-04-14

Creates the v0 storage schema. See ``schemas/storage/`` for the
authoritative ORM models; this migration is the DDL realisation.

Note on autogenerate: server_default values (``now()``, ``'{}'``) and
CHECK constraints are not always captured faithfully by Alembic
autogenerate. Every future revision that touches these should be
hand-reviewed before ``upgrade head``.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- tenants ------------------------------------------------------- #
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
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
        sa.CheckConstraint(
            "length(default_currency) = 3", name="ck_tenants_currency_len"
        ),
    )
    op.create_index("ix_tenants_display_name", "tenants", ["display_name"])

    # ----- tenant_credentials ------------------------------------------- #
    op.create_table(
        "tenant_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_blob", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rotated_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
    op.create_index(
        "ix_tenant_credentials_tenant_id", "tenant_credentials", ["tenant_id"]
    )
    op.create_index(
        "ux_tenant_credentials_provider",
        "tenant_credentials",
        ["tenant_id", "provider"],
        unique=True,
    )

    # ----- users --------------------------------------------------------- #
    user_role = postgresql.ENUM(
        "agency_admin",
        "ticketing_lead",
        "accounting_lead",
        "agent",
        "viewer",
        name="user_role",
        # Already created via explicit .create() below; passing
        # create_type=False prevents SQLAlchemy from emitting a second
        # CREATE TYPE when this enum is referenced by op.create_table.
        create_type=False,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            user_role,
            nullable=False,
            server_default="agent",
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
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index(
        "ux_users_tenant_external",
        "users",
        ["tenant_id", "external_id"],
        unique=True,
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ----- sessions ------------------------------------------------------ #
    actor_kind = postgresql.ENUM(
        "human", "agent", "system", name="actor_kind", create_type=False
    )
    actor_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_kind",
            actor_kind,
            nullable=False,
            server_default="human",
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
    op.create_index("ix_sessions_tenant_id", "sessions", ["tenant_id"])
    op.create_index("ix_sessions_actor_id", "sessions", ["actor_id"])
    op.create_index(
        "ix_sessions_tenant_created", "sessions", ["tenant_id", "created_at"]
    )

    # ----- messages ------------------------------------------------------ #
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "session_id", "sequence", name="ux_messages_session_seq"
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index(
        "ix_messages_session_seq", "messages", ["session_id", "sequence"]
    )

    # ----- pending_approvals -------------------------------------------- #
    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=False),
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pending_approvals_session_id",
        "pending_approvals",
        ["session_id"],
    )
    op.create_index(
        "ix_pending_approvals_session",
        "pending_approvals",
        ["session_id", "requested_at"],
    )

    # ----- audit_events -------------------------------------------------- #
    audit_status = postgresql.ENUM(
        "started",
        "succeeded",
        "failed",
        "rejected",
        "cancelled",
        name="audit_status",
        create_type=False,
    )
    audit_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_kind", actor_kind, nullable=False),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("driver", sa.String(length=64), nullable=True),
        sa.Column(
            "entity_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "inputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "outputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "completed_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "status",
            audit_status,
            nullable=False,
            server_default="started",
        ),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_tool", "audit_events", ["tool"])
    op.create_index(
        "ix_audit_tenant_started", "audit_events", ["tenant_id", "started_at"]
    )
    op.create_index(
        "ix_audit_tenant_tool_started",
        "audit_events",
        ["tenant_id", "tool", "started_at"],
    )
    op.create_index("ix_audit_status", "audit_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_audit_status", table_name="audit_events")
    op.drop_index("ix_audit_tenant_tool_started", table_name="audit_events")
    op.drop_index("ix_audit_tenant_started", table_name="audit_events")
    op.drop_index("ix_audit_events_tool", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.execute("DROP TYPE IF EXISTS audit_status")

    op.drop_index("ix_pending_approvals_session", table_name="pending_approvals")
    op.drop_index("ix_pending_approvals_session_id", table_name="pending_approvals")
    op.drop_table("pending_approvals")

    op.drop_index("ix_messages_session_seq", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_sessions_tenant_created", table_name="sessions")
    op.drop_index("ix_sessions_actor_id", table_name="sessions")
    op.drop_index("ix_sessions_tenant_id", table_name="sessions")
    op.drop_table("sessions")
    op.execute("DROP TYPE IF EXISTS actor_kind")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ux_users_tenant_external", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")

    op.drop_index(
        "ux_tenant_credentials_provider", table_name="tenant_credentials"
    )
    op.drop_index(
        "ix_tenant_credentials_tenant_id", table_name="tenant_credentials"
    )
    op.drop_table("tenant_credentials")

    op.drop_index("ix_tenants_display_name", table_name="tenants")
    op.drop_table("tenants")
