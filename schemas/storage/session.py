"""Session + message + pending-approval storage tables.

These rows mirror the canonical ``Session``, ``Message``, and
``PendingApproval`` Pydantic models used by the agent runtime. The
storage layer flattens the Pydantic in-memory structure into three
relational tables so individual messages and approvals can be queried
and paginated independently of the parent session.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import JSON

from .base import Base, Timestamps, tenant_id_fk, uuid_pk


def _jsonb():  # type: ignore[no-untyped-def]
    """Return a JSONB column type that falls back to JSON on SQLite."""
    return JSONB().with_variant(JSON(), "sqlite")


class ActorKindEnum(str, enum.Enum):
    """Mirror of :class:`schemas.canonical.ActorKind`."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


# Shared SAEnum instance used by both SessionRow and AuditEventRow so the
# Postgres enum type ``actor_kind`` is created exactly once. The alembic
# migration owns CREATE TYPE — the model never auto-creates schema
# (``create_type=False``) and ``values_callable`` makes SQLAlchemy emit the
# enum's lowercase ``value`` rather than the uppercase Python member name,
# which Postgres rejects.
ACTOR_KIND_SATYPE = SAEnum(
    ActorKindEnum,
    name="actor_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class ApprovalStatusEnum(str, enum.Enum):
    """Mirror of :data:`voyagent_agent_runtime.session.ApprovalStatus`."""

    PENDING = "pending"
    GRANTED = "granted"
    REJECTED = "rejected"
    EXPIRED = "expired"


# Matching rationale as ACTOR_KIND_SATYPE: migration owns CREATE TYPE,
# and we emit the lowercase ``value`` so Postgres accepts it.
APPROVAL_STATUS_SATYPE = SAEnum(
    ApprovalStatusEnum,
    name="approval_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class SessionRow(Base, Timestamps):
    """One chat session — the persistent shell around a conversation."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Nullable so the session survives user deletion (e.g., "
        "offboarded employee). actor_kind still distinguishes agent / "
        "system sessions that have no user row.",
    )
    actor_kind: Mapped[ActorKindEnum] = mapped_column(
        ACTOR_KIND_SATYPE,
        nullable=False,
        server_default=ActorKindEnum.HUMAN.value,
    )

    __table_args__ = (
        Index("ix_sessions_tenant_created", "tenant_id", "created_at"),
    )


class MessageRow(Base):
    """One message inside a session. Immutable once written."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[list[dict]] = mapped_column(
        _jsonb(),
        nullable=False,
        doc="Anthropic-shaped content blocks: text, tool_use, tool_result, ...",
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="ux_messages_session_seq"),
        Index("ix_messages_session_seq", "session_id", "sequence"),
    )


class PendingApprovalRow(Base):
    """One approval request the runtime is waiting on.

    Primary key is the approval id (``ap-<turn_id>-<tool_name>``) that
    the runtime mints — keeping it as the PK means the same approval
    across retries maps to the same row without a lookup.
    """

    __tablename__ = "pending_approvals"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(nullable=False)
    granted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Nullable on the ORM so backfills of old rows don't fail validation;
    # the alembic migration enforces NOT NULL after the backfill lands.
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[ApprovalStatusEnum] = mapped_column(
        APPROVAL_STATUS_SATYPE,
        nullable=False,
        server_default=ApprovalStatusEnum.PENDING.value,
    )

    __table_args__ = (
        Index("ix_pending_approvals_session", "session_id", "requested_at"),
        Index("ix_pending_approvals_status_expires", "status", "expires_at"),
    )


__all__ = [
    "ActorKindEnum",
    "ApprovalStatusEnum",
    "APPROVAL_STATUS_SATYPE",
    "MessageRow",
    "PendingApprovalRow",
    "SessionRow",
]
