"""Tenant users.

Users authenticate against Voyagent's in-house auth service. The
``password_hash`` column carries an argon2id PHC string; ``email`` is
the primary login identifier and is therefore globally unique across
all tenants — two tenants cannot both own a user with email
``alice@example.com``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, Index, String, TIMESTAMP, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, tenant_id_fk, uuid_pk


class UserRole(str, enum.Enum):
    """Coarse role assigned to each human user.

    Mirrors the role list the runtime's approval gating references
    (``agency_admin``, ``ticketing_lead``). Finer-grained capability
    checks live in the approval_roles list on individual ToolSpecs.
    """

    AGENCY_ADMIN = "agency_admin"
    TICKETING_LEAD = "ticketing_lead"
    ACCOUNTING_LEAD = "accounting_lead"
    AGENT = "agent"
    VIEWER = "viewer"


class User(Base, Timestamps):
    """A human user attached to a tenant.

    ``email`` is globally unique across the whole system — it is the
    canonical login identifier for in-house auth. ``external_id`` is
    retained for legacy IDP-issued ids (nullable for newly self-served
    users) so existing rows from earlier IDP-driven provisioning still
    fit the schema.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        # values_callable maps the Python enum to its DB value
        # (``agency_admin``) instead of the default member name
        # (``AGENCY_ADMIN``), which the Postgres enum rejects.
        # create_type=False because the alembic migration owns the
        # CREATE TYPE — the model never auto-creates schema.
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_type=False,
        ),
        nullable=False,
        server_default=UserRole.AGENT.value,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    # TOTP 2FA. ``totp_secret`` is the base32-encoded shared secret the
    # authenticator app holds. Nullable until the user kicks off setup.
    # ``totp_enabled`` only flips true after a successful first-verify.
    #
    # TODO(security): encrypt ``totp_secret`` at rest using
    # ``VOYAGENT_KMS_KEY`` (see schemas.storage.crypto.FernetEnvKMS). For
    # v0 we store the base32 plaintext so the flow is testable without
    # wiring the KMS into every sign-in path. Follow-up ticket.
    totp_secret: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ux_users_email",
            "email",
            unique=True,
        ),
        Index("ix_users_tenant_external", "tenant_id", "external_id"),
    )


__all__ = ["User", "UserRole"]
