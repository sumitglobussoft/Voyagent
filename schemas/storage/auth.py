"""In-house authentication storage models.

This module owns the rows that the in-house auth service writes
directly. Today that is just :class:`RefreshTokenRow` — a hashed
refresh-token store used to back the ``POST /auth/refresh`` endpoint.

The plain refresh token never hits the database; only its
``sha256`` digest is persisted, so a database leak does not yield
session-takeover material on its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, LargeBinary, String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType, uuid7


class RefreshTokenRow(Base, Timestamps):
    """A single hashed refresh token for one user session.

    * ``token_hash`` is the sha256 of the opaque base64url token returned
      to the client. We index by hash so refresh lookups are O(1) and
      so the plain token is never recoverable from the table.
    * ``revoked_at`` is set when the token is rotated (sign-in returns a
      new pair, refresh single-uses the old, sign-out kills it
      explicitly). ``find_active`` filters this out.
    * ``user_agent`` / ``ip`` are best-effort metadata captured at issue
      time so admins can audit "where is this session coming from".
    """

    __tablename__ = "auth_refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid7,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_auth_refresh_tokens_user_expires",
            "user_id",
            "expires_at",
        ),
    )


__all__ = ["RefreshTokenRow"]
