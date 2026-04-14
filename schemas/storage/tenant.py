"""Tenant + per-tenant credential rows.

A Voyagent deployment is multi-tenant from day one. Every domain row
references a tenant, and every vendor integration (Amadeus, Tally, a
BSP portal) carries encrypted per-tenant credentials. Credentials are
stored as opaque ciphertext; encryption keys and rotation policy are a
different agent's concern — this module only pins the shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import JSON

from .base import Base, Timestamps, tenant_id_fk, uuid_pk


def _jsonb():  # type: ignore[no-untyped-def]
    """Return JSONB on Postgres; JSON on portable dialects (SQLite tests)."""
    return JSONB().with_variant(JSON(), "sqlite")


class Tenant(Base, Timestamps):
    """A top-level tenant (travel agency)."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        doc="ISO-4217 default currency for UI display. Not a business rule — "
        "individual bookings always store their own currency.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    __table_args__ = (
        CheckConstraint(
            "length(default_currency) = 3",
            name="ck_tenants_currency_len",
        ),
        Index("ix_tenants_display_name", "display_name"),
    )


class TenantCredential(Base, Timestamps):
    """Encrypted per-tenant credentials for a named provider.

    ``encrypted_blob`` is opaque ciphertext; ``nonce`` is the associated
    nonce/IV. The decryption key lives in a KMS the credential agent
    will own. At this layer we only track shape and rotation.

    TODO(voyagent-credentials): wire a KMS-backed envelope encryption
    service and migrate existing rows. Until then application code
    should treat ``encrypted_blob`` as unreadable.
    """

    __tablename__ = "tenant_credentials"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Free-form provider id — e.g., 'amadeus', 'tally', 'bsp_india'.",
    )
    encrypted_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    meta: Mapped[dict] = mapped_column(
        _jsonb(),
        nullable=False,
        server_default="{}",
        doc="Non-secret metadata the caller needs to use the credential "
        "(e.g., API base URL, account id). Never put secrets here.",
    )
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "ux_tenant_credentials_provider",
            "tenant_id",
            "provider",
            unique=True,
        ),
    )


__all__ = ["Tenant", "TenantCredential"]
