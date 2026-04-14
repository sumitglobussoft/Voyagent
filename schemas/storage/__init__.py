"""Voyagent storage schema — SQLAlchemy 2.0 mapped classes.

This package is the *persistence* mirror of :mod:`schemas.canonical`.
Canonical is what the agent runtime speaks; storage is how we
physically persist and index rows. Keep the two packages separate:
storage additions should not leak into canonical, and canonical
additions should not imply a migration.

Re-exports every public model plus :class:`Base` so callers can write
``from schemas.storage import Base, SessionRow, AuditEventRow``.
"""

from __future__ import annotations

from .audit import AuditEventRow, AuditStatusEnum
from .auth import RefreshTokenRow
from .base import Base, Timestamps, UUIDType, tenant_id_fk, uuid7, uuid_pk
from .credentials import (
    CredentialPayload,
    TenantCredentialRepository,
    resolve_tenant_credentials,
    set_repository_for_test,
)
from .crypto import (
    CredentialDecryptionError,
    FernetEnvKMS,
    KMSConfigurationError,
    KMSProvider,
    NullKMS,
    SecurityError,
    build_kms_provider,
)
from .passenger import PassengerRow
from .session import (
    ACTOR_KIND_SATYPE,
    ActorKindEnum,
    MessageRow,
    PendingApprovalRow,
    SessionRow,
)
from .tenant import Tenant, TenantCredential
from .user import User, UserRole

__all__ = [
    "ACTOR_KIND_SATYPE",
    "ActorKindEnum",
    "AuditEventRow",
    "AuditStatusEnum",
    "Base",
    "CredentialDecryptionError",
    "CredentialPayload",
    "FernetEnvKMS",
    "KMSConfigurationError",
    "KMSProvider",
    "MessageRow",
    "NullKMS",
    "PassengerRow",
    "PendingApprovalRow",
    "RefreshTokenRow",
    "SecurityError",
    "SessionRow",
    "Tenant",
    "TenantCredential",
    "TenantCredentialRepository",
    "Timestamps",
    "UUIDType",
    "User",
    "UserRole",
    "build_kms_provider",
    "resolve_tenant_credentials",
    "set_repository_for_test",
    "tenant_id_fk",
    "uuid7",
    "uuid_pk",
]
