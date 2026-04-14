"""Enquiry storage table.

A customer travel enquiry is the earliest artifact in the agency's
pipeline — an agent talks to a walk-in / phone-in / email-in prospect
and logs their intent (origin, destination, dates, pax, budget, free-
form notes). Once promoted, an enquiry gets an attached chat session
the agentic runtime uses to actually plan + price the trip.

Tenant isolation: ``tenant_id`` is required, indexed, and every read
path MUST filter by it. The compound index on ``(tenant_id, status,
created_at DESC)`` fits the default list query (tenant-scoped, most-
recent-first, optional status filter) and keeps it cheap.

The ``session_id`` column is **not** a foreign key to ``sessions.id``.
Sessions and enquiries live in the same schema today but may drift as
the chat surface evolves; leaving the link unconstrained lets either
side be cleared / archived without cascade surprises.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Date,
    Enum as SAEnum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType, tenant_id_fk, uuid_pk


class EnquiryStatusEnum(str, enum.Enum):
    """Workflow status for a customer travel enquiry."""

    NEW = "new"
    QUOTED = "quoted"
    BOOKED = "booked"
    CANCELLED = "cancelled"


# Shared SAEnum so the Postgres enum type ``enquiry_status`` is created
# exactly once. ``create_type=False`` — the alembic migration owns the
# CREATE TYPE.
ENQUIRY_STATUS_SATYPE = SAEnum(
    EnquiryStatusEnum,
    name="enquiry_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


# Numeric(14, 2) matches invoices / bills — more than enough headroom
# for a single enquiry's budget on any supported backend.
_AMOUNT_TYPE = Numeric(14, 2)


class EnquiryRow(Base, Timestamps):
    """One customer enquiry logged by an agent."""

    __tablename__ = "enquiries"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()

    # No FK constraint on created_by_user_id — keeping it soft lets us
    # preserve historical enquiries even if the logging user row is
    # later deleted / off-boarded. The UUID reference is sufficient for
    # audit queries.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        nullable=False,
        index=True,
    )

    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)

    depart_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    pax_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    budget_amount: Mapped[Decimal | None] = mapped_column(
        _AMOUNT_TYPE, nullable=True
    )
    budget_currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)

    status: Mapped[EnquiryStatusEnum] = mapped_column(
        ENQUIRY_STATUS_SATYPE,
        nullable=False,
        default=EnquiryStatusEnum.NEW,
        server_default=EnquiryStatusEnum.NEW.value,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft link to the chat session (set once the enquiry is promoted).
    # Not a FK — see module docstring.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(), nullable=True
    )

    __table_args__ = (
        # Fits the default list query: tenant-scoped, optional status
        # filter, ordered by created_at desc. ``created_at`` is provided
        # by :class:`Timestamps`.
        Index(
            "ix_enquiries_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
    )


__all__ = [
    "ENQUIRY_STATUS_SATYPE",
    "EnquiryRow",
    "EnquiryStatusEnum",
]
