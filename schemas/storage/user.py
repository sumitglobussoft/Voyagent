"""Tenant users.

Users authenticate through an upstream identity provider (Clerk in v0);
``external_id`` is the stable id the IDP mints. ``role`` is a
coarse-grained enum — fine-grained authorisation is enforced per tool by
the agent runtime, not by the user row.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum, Index, String
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

    ``external_id`` is unique per tenant — two tenants may both have a
    user with external_id ``usr_abc`` if those happen to be distinct
    accounts upstream.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        server_default=UserRole.AGENT.value,
    )

    __table_args__ = (
        Index(
            "ux_users_tenant_external",
            "tenant_id",
            "external_id",
            unique=True,
        ),
        Index("ix_users_email", "email"),
    )


__all__ = ["User", "UserRole"]
