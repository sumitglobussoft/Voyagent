"""Passenger storage table.

Persists the subset of :class:`schemas.canonical.Passenger` +
:class:`schemas.canonical.Passport` that the runtime needs to resolve a
traveler by identity. The canonical model is richer (multiple phones,
national ids, localized notes); storage keeps the tenant-scoped lookup
columns and leans on the canonical objects for the rest when loaded.

Tenant isolation is enforced by two things working together: the
``tenant_id`` foreign key cascades on tenant delete, and every query in
:class:`voyagent_agent_runtime.passenger_resolver.StoragePassengerResolver`
is ``WHERE tenant_id = :tid``. Unique indexes are scoped
``(tenant_id, ...)`` so two tenants may own the same email or passport
number without collision.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, tenant_id_fk, uuid_pk


class PassengerRow(Base, Timestamps):
    """One traveler scoped to a tenant.

    The column set is deliberately the tenant-scoped identity minimum —
    enough for ``find_by_email`` / ``find_by_passport`` and the upsert
    path the agent runtime drives when it materialises a passenger
    mid-turn. Broader attributes (phones list, addresses, national ids)
    will land as child tables in a later migration; the resolver today
    reconstructs a canonical :class:`~schemas.canonical.Passenger` from
    the columns present here.
    """

    __tablename__ = "passengers"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    passport_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    passport_expiry: Mapped[date | None] = mapped_column(nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Unique indexes are composite on (tenant_id, ...). NULLs compare as
    # distinct under the SQL standard, so passengers without a captured
    # email / passport do not collide.
    __table_args__ = (
        Index(
            "ux_passengers_tenant_email",
            "tenant_id",
            "email",
            unique=True,
        ),
        Index(
            "ux_passengers_tenant_passport",
            "tenant_id",
            "passport_number",
            unique=True,
        ),
        Index("ix_passengers_tenant_created", "tenant_id", "created_at"),
    )


__all__ = ["PassengerRow"]
