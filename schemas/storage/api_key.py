"""API keys for headless access.

API keys let scripts, CI jobs, and external integrations authenticate
without a human login flow. Each row stores:

* ``prefix``: the first 8 urlsafe chars of the key, displayed in the
  UI and used as an O(1) lookup index.
* ``key_hash``: SHA-256 hex digest of the full ``vy_<prefix>_<body>``
  string. The plaintext is returned to the user exactly once at
  creation; never stored, never retrievable.
* ``scopes``: v0 supports only ``["full"]``. Retained as a text column
  so future scope expansion is a data migration, not a schema change.

Revocation is soft (``revoked_at``); expired + revoked keys are
rejected by the verification path. ``last_used_at`` is updated on
every successful request for usage/rotation UX.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType, tenant_id_fk, uuid7


class ApiKeyRow(Base, Timestamps):
    """A hashed API key owned by a tenant + created by one user."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid7
    )
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 8-char urlsafe prefix — stored plaintext so the UI can show it
    # and so lookup is O(1) via the index on this column.
    prefix: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )
    # SHA-256 hex of the full ``vy_<prefix>_<body>`` plaintext (64 chars).
    key_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    # Comma-separated scope list. v0 uses just ``"full"``. Kept as a
    # plain text column so SQLite tests and Postgres agree on the shape
    # — Postgres array types don't round-trip through aiosqlite.
    scopes: Mapped[str] = mapped_column(
        String(255), nullable=False, default="full"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_api_keys_tenant_revoked",
            "tenant_id",
            "revoked_at",
        ),
    )


__all__ = ["ApiKeyRow"]
