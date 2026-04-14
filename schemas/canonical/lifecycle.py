"""Lifecycle — v0.

Enquiry (the cross-cutting record that enters the system first), Document
(any uploaded artifact), and AuditEvent (every side-effect tool call).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .primitives import EntityId, LocalizedText, Timestamps, _strict


# --------------------------------------------------------------------------- #
# Enquiry                                                                     #
# --------------------------------------------------------------------------- #


class EnquiryDomain(StrEnum):
    TICKETING = "ticketing"
    HOTELS_HOLIDAYS = "hotels_holidays"
    VISA = "visa"
    MIXED = "mixed"


class EnquiryStatus(StrEnum):
    NEW = "new"
    GATHERING = "gathering"           # identify & collect tier in progress
    QUOTED = "quoted"
    REVISING = "revising"
    APPROVED = "approved"
    BOOKED = "booked"
    CLOSED = "closed"
    LOST = "lost"


class Enquiry(Timestamps):
    """The root record for every conversation the agent has with a client.

    `requirements` is deliberately a loose dict at v0. v1 will promote
    frequently-used keys into a typed schema per EnquiryDomain; keeping it
    loose now lets drivers and domain agents evolve without schema churn.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId
    client_id: EntityId

    domain: EnquiryDomain
    status: EnquiryStatus = EnquiryStatus.NEW

    requirements: dict[str, Any] = Field(default_factory=dict)
    passenger_ids: list[EntityId] = Field(default_factory=list)

    itinerary_ids: list[EntityId] = Field(default_factory=list)
    fare_ids: list[EntityId] = Field(default_factory=list)
    booking_ids: list[EntityId] = Field(default_factory=list)

    assigned_user_id: EntityId | None = None
    notes: LocalizedText | None = None


# --------------------------------------------------------------------------- #
# Document                                                                    #
# --------------------------------------------------------------------------- #


class DocumentKind(StrEnum):
    PASSPORT_SCAN = "passport_scan"
    VISA_COPY = "visa_copy"
    PHOTO = "photo"
    BANK_STATEMENT = "bank_statement"
    SALARY_SLIP = "salary_slip"
    EMPLOYMENT_LETTER = "employment_letter"
    ITR = "itr"
    SUPPORTING_DOC = "supporting_doc"
    TICKET = "ticket"
    VOUCHER = "voucher"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    SUPPLIER_BILL = "supplier_bill"
    BSP_STATEMENT = "bsp_statement"
    BANK_RECON_STATEMENT = "bank_recon_statement"
    CARD_STATEMENT = "card_statement"
    OTHER = "other"


class Document(Timestamps):
    """A file stored against some entities.

    `links` carries back-references to anything the document pertains to:
    {'passenger_id': ..., 'visa_file_id': ..., 'invoice_id': ...}. We do not
    enforce which keys are valid at this layer — that's a runtime concern.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    kind: DocumentKind
    filename: str
    content_type: str = Field(description="MIME type as reported by the uploader.")
    size_bytes: int = Field(ge=0)

    storage_uri: str = Field(description="Opaque URI into the object store (e.g. 's3://voyagent-docs/<tenant>/<id>').")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    uploaded_by: EntityId
    links: dict[str, EntityId] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Audit                                                                       #
# --------------------------------------------------------------------------- #


class ActorKind(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class AuditStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"     # approval denied
    CANCELLED = "cancelled"


class AuditEvent(BaseModel):
    """One side-effect tool invocation. The audit log is append-only.

    Every tool with `side_effect=True` writes an AuditEvent. Approval
    decisions, driver identity, inputs, and outputs are all recorded so the
    work is replayable and reviewable long after the fact.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    actor_id: EntityId
    actor_kind: ActorKind

    tool: str = Field(description="Canonical tool name: 'issue_ticket', 'post_journal_entry', ...")
    driver: str | None = Field(default=None, description="Driver that executed the side effect, if any.")

    entity_refs: dict[str, EntityId] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    approval_required: bool = False
    approved_by: EntityId | None = None
    approved_at: datetime | None = None

    started_at: datetime
    completed_at: datetime | None = None
    status: AuditStatus = AuditStatus.STARTED


__all__ = [
    "ActorKind",
    "AuditEvent",
    "AuditStatus",
    "Document",
    "DocumentKind",
    "Enquiry",
    "EnquiryDomain",
    "EnquiryStatus",
]
