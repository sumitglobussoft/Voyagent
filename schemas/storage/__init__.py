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

from .api_key import ApiKeyRow
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
from .enquiry import (
    ENQUIRY_STATUS_SATYPE,
    EnquiryRow,
    EnquiryStatusEnum,
)
from .invite import InviteRow, InviteStatusEnum
from .invoice import (
    BILL_STATUS_SATYPE,
    INVOICE_STATUS_SATYPE,
    BillRow,
    BillStatusEnum,
    InvoiceRow,
    InvoiceStatusEnum,
)
from .ledger import (
    LEDGER_ACCOUNT_TYPE_SATYPE,
    JournalEntryRow,
    JournalLine,
    LedgerAccountRow,
    LedgerAccountTypeEnum,
    UnbalancedJournalEntryError,
    build_journal_entry,
)
from .passenger import PassengerRow
from .session_cost import SessionCostRow
from .tenant_settings import TenantSettingsRow
from .session import (
    ACTOR_KIND_SATYPE,
    APPROVAL_STATUS_SATYPE,
    ActorKindEnum,
    ApprovalStatusEnum,
    MessageRow,
    PendingApprovalRow,
    SessionRow,
)
from .tenant import Tenant, TenantCredential
from .user import User, UserRole

__all__ = [
    "ACTOR_KIND_SATYPE",
    "APPROVAL_STATUS_SATYPE",
    "ApiKeyRow",
    "ActorKindEnum",
    "ApprovalStatusEnum",
    "AuditEventRow",
    "AuditStatusEnum",
    "BILL_STATUS_SATYPE",
    "Base",
    "BillRow",
    "BillStatusEnum",
    "CredentialDecryptionError",
    "CredentialPayload",
    "ENQUIRY_STATUS_SATYPE",
    "EnquiryRow",
    "EnquiryStatusEnum",
    "FernetEnvKMS",
    "INVOICE_STATUS_SATYPE",
    "InviteRow",
    "InviteStatusEnum",
    "InvoiceRow",
    "InvoiceStatusEnum",
    "JournalEntryRow",
    "JournalLine",
    "KMSConfigurationError",
    "KMSProvider",
    "LEDGER_ACCOUNT_TYPE_SATYPE",
    "LedgerAccountRow",
    "LedgerAccountTypeEnum",
    "MessageRow",
    "NullKMS",
    "PassengerRow",
    "PendingApprovalRow",
    "RefreshTokenRow",
    "SecurityError",
    "SessionCostRow",
    "SessionRow",
    "Tenant",
    "TenantSettingsRow",
    "TenantCredential",
    "TenantCredentialRepository",
    "Timestamps",
    "UUIDType",
    "UnbalancedJournalEntryError",
    "User",
    "UserRole",
    "build_journal_entry",
    "build_kms_provider",
    "resolve_tenant_credentials",
    "set_repository_for_test",
    "tenant_id_fk",
    "uuid7",
    "uuid_pk",
]
