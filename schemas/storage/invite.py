"""Team-invite rows.

Invites let an agency_admin add a teammate to an existing tenant
without going through sign-up (which always mints a fresh tenant).
The row stores only a ``token_hash`` — the plain opaque token is
returned once at creation time and emailed (TODO: SMTP) to the
invitee. Accept-invite looks the row up by hash and creates a user
in the invite's tenant with the invited role.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType, tenant_id_fk, uuid7


class InviteStatusEnum(str, enum.Enum):
    """Lifecycle states for a team invite."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InviteRow(Base, Timestamps):
    """Opaque-token invite into an existing tenant."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid7
    )
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="agent"
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    status: Mapped[InviteStatusEnum] = mapped_column(
        SAEnum(
            InviteStatusEnum,
            name="invite_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_type=False,
        ),
        nullable=False,
        server_default=InviteStatusEnum.PENDING.value,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ux_invites_tenant_email_lower",
            "tenant_id",
            text("lower(email)"),
            unique=True,
        ),
        Index("ix_invites_tenant_status", "tenant_id", "status"),
    )


__all__ = ["InviteRow", "InviteStatusEnum"]
