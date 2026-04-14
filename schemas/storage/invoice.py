"""Invoice + Bill storage tables.

Two near-identical ledger-adjacent document tables:

* :class:`InvoiceRow` — money owed to the agency by its customers.
* :class:`BillRow`    — money the agency owes to vendors (airlines via BSP,
  hotels, visa agents).

These are the human-readable document layer. The double-entry posting
layer lives in :mod:`schemas.storage.ledger`. Reports usually hit this
table directly because aging analysis is document-centric; the ledger
is there for trial-balance / GL reports later.

Tenant isolation: ``tenant_id`` is required on every row, indexed, and
every unique constraint is composite on ``(tenant_id, ...)`` so two
tenants may independently use the same invoice number. All read paths
MUST filter by ``tenant_id`` — there is no global view.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum as SAEnum,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, tenant_id_fk, uuid_pk


# --------------------------------------------------------------------------- #
# Enums                                                                       #
# --------------------------------------------------------------------------- #


class InvoiceStatusEnum(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"


class BillStatusEnum(str, enum.Enum):
    DRAFT = "draft"
    RECEIVED = "received"
    SCHEDULED = "scheduled"
    PAID = "paid"
    VOID = "void"


INVOICE_STATUS_SATYPE = SAEnum(
    InvoiceStatusEnum,
    name="invoice_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BILL_STATUS_SATYPE = SAEnum(
    BillStatusEnum,
    name="bill_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


# Money columns use Numeric(14, 2) — never float. 14 digits with 2
# fractional gives us up to 999,999,999,999.99 in any currency, which
# is more headroom than an agency will ever need per document and still
# fits a decimal(14,2) on every supported backend.
_AMOUNT_TYPE = Numeric(14, 2)


# --------------------------------------------------------------------------- #
# InvoiceRow                                                                  #
# --------------------------------------------------------------------------- #


class InvoiceRow(Base, Timestamps):
    """Customer-facing invoice — receivable from the agency's clients."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()

    number: Mapped[str] = mapped_column(String(64), nullable=False)
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_amount: Mapped[Decimal] = mapped_column(_AMOUNT_TYPE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        _AMOUNT_TYPE,
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    status: Mapped[InvoiceStatusEnum] = mapped_column(
        INVOICE_STATUS_SATYPE,
        nullable=False,
        server_default=InvoiceStatusEnum.DRAFT.value,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "number", name="ux_invoices_tenant_number"
        ),
        Index(
            "ix_invoices_tenant_status_due",
            "tenant_id",
            "status",
            "due_date",
        ),
        Index("ix_invoices_tenant_issue", "tenant_id", "issue_date"),
    )


# --------------------------------------------------------------------------- #
# BillRow                                                                     #
# --------------------------------------------------------------------------- #


class BillRow(Base, Timestamps):
    """Vendor-facing bill — payable to airlines, hotels, visa agents."""

    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()

    number: Mapped[str] = mapped_column(String(64), nullable=False)
    # vendor_reference is the supplier's own invoice number (e.g. the BSP
    # memo id). Keeping it distinct from ``number`` lets the agency own
    # its internal numbering while still detecting duplicate supplier
    # documents — which is the thing you actually want to prevent.
    vendor_reference: Mapped[str] = mapped_column(String(128), nullable=False)

    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_amount: Mapped[Decimal] = mapped_column(_AMOUNT_TYPE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        _AMOUNT_TYPE,
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    status: Mapped[BillStatusEnum] = mapped_column(
        BILL_STATUS_SATYPE,
        nullable=False,
        server_default=BillStatusEnum.DRAFT.value,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "vendor_reference",
            name="ux_bills_tenant_vendor_reference",
        ),
        Index(
            "ix_bills_tenant_status_due",
            "tenant_id",
            "status",
            "due_date",
        ),
        Index("ix_bills_tenant_issue", "tenant_id", "issue_date"),
    )


__all__ = [
    "BILL_STATUS_SATYPE",
    "INVOICE_STATUS_SATYPE",
    "BillRow",
    "BillStatusEnum",
    "InvoiceRow",
    "InvoiceStatusEnum",
]
