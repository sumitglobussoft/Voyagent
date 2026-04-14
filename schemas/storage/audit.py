"""Audit-event storage.

Mirrors :class:`schemas.canonical.AuditEvent`. Append-only in spirit —
the model never deletes rows, but we do update ``status`` from STARTED
to SUCCEEDED / FAILED / REJECTED when the tool call completes, which is
a controlled transition, not a free-form mutation.

Amadeus offer caching lives in Redis, not in Postgres — see
``offer_cache.py`` in :mod:`voyagent_agent_runtime`. Offers have a
natural 15–30 minute TTL and keying them by canonical Fare id is
enough; the relational audit trail still records every ``create`` call
that used them.
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
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import JSON

from .base import Base, tenant_id_fk, uuid_pk
from .session import ACTOR_KIND_SATYPE, ActorKindEnum


def _jsonb():  # type: ignore[no-untyped-def]
    """Return a JSONB column type that falls back to JSON on SQLite."""
    return JSONB().with_variant(JSON(), "sqlite")


class AuditStatusEnum(str, enum.Enum):
    """Mirror of :class:`schemas.canonical.AuditStatus`."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AuditEventRow(Base):
    """One side-effect tool invocation."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Nullable because system-initiated events have no user row.",
    )
    actor_kind: Mapped[ActorKindEnum] = mapped_column(
        ACTOR_KIND_SATYPE,
        nullable=False,
    )

    tool: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    driver: Mapped[str | None] = mapped_column(String(64), nullable=True)

    entity_refs: Mapped[dict] = mapped_column(
        _jsonb(), nullable=False, server_default="{}"
    )
    inputs: Mapped[dict] = mapped_column(
        _jsonb(), nullable=False, server_default="{}"
    )
    outputs: Mapped[dict] = mapped_column(
        _jsonb(), nullable=False, server_default="{}"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[AuditStatusEnum] = mapped_column(
        SAEnum(
            AuditStatusEnum,
            name="audit_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_type=False,
        ),
        nullable=False,
        server_default=AuditStatusEnum.STARTED.value,
    )

    __table_args__ = (
        Index("ix_audit_tenant_started", "tenant_id", "started_at"),
        Index("ix_audit_tenant_tool_started", "tenant_id", "tool", "started_at"),
        Index("ix_audit_status", "status"),
    )


__all__ = ["AuditEventRow", "AuditStatusEnum"]
