"""Round-trip, default-value, and index tests for :mod:`schemas.storage.enquiry`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import (
    EnquiryRow,
    EnquiryStatusEnum,
    Tenant,
    uuid7,
)

pytestmark = pytest.mark.asyncio


async def test_enquiry_round_trip_preserves_fields(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()
    user_id = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_id, display_name="Acme Travel", default_currency="INR"
                )
            )
            db.add(
                EnquiryRow(
                    tenant_id=tenant_id,
                    created_by_user_id=user_id,
                    customer_name="Alice Example",
                    customer_email="alice@example.com",
                    customer_phone="+91-99999-11111",
                    origin="DEL",
                    destination="DXB",
                    depart_date=date(2026, 6, 1),
                    return_date=date(2026, 6, 10),
                    pax_count=2,
                    budget_amount=Decimal("75000.50"),
                    budget_currency="INR",
                    status=EnquiryStatusEnum.QUOTED,
                    notes="VIP — window seats preferred.",
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(EnquiryRow).where(
                    EnquiryRow.customer_name == "Alice Example"
                )
            )
        ).scalar_one()
        assert row.tenant_id == tenant_id
        assert row.created_by_user_id == user_id
        assert row.customer_email == "alice@example.com"
        assert row.origin == "DEL"
        assert row.destination == "DXB"
        assert row.depart_date == date(2026, 6, 1)
        assert row.return_date == date(2026, 6, 10)
        assert row.pax_count == 2
        assert row.budget_amount == Decimal("75000.50")
        assert row.budget_currency == "INR"
        assert row.status == EnquiryStatusEnum.QUOTED
        assert row.notes == "VIP — window seats preferred."
        assert row.session_id is None
        assert row.created_at is not None
        assert row.updated_at is not None


async def test_enquiry_default_values(engine: AsyncEngine) -> None:
    """Minimal insert — only NOT NULL fields supplied — gets server defaults."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_id, display_name="Agency", default_currency="USD"
                )
            )
            db.add(
                EnquiryRow(
                    tenant_id=tenant_id,
                    created_by_user_id=uuid7(),
                    customer_name="Walk-in",
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(EnquiryRow).where(
                    EnquiryRow.customer_name == "Walk-in"
                )
            )
        ).scalar_one()
        # Defaults populated by the model + server.
        assert row.pax_count == 1
        assert row.status == EnquiryStatusEnum.NEW
        # Nullable columns remain null.
        assert row.origin is None
        assert row.destination is None
        assert row.depart_date is None
        assert row.return_date is None
        assert row.budget_amount is None
        assert row.budget_currency is None
        assert row.notes is None
        assert row.session_id is None


async def test_enquiry_enum_rejects_invalid_status() -> None:
    """The Python enum itself must refuse bad values.

    We don't round-trip through SQLite here because SQLite's fallback
    enum check isn't as strict as Postgres's — the Python-side check
    is the primary guard.
    """
    with pytest.raises(ValueError):
        EnquiryStatusEnum("not-a-status")


async def test_enquiry_tenant_isolation(engine: AsyncEngine) -> None:
    """A query filtered by ``tenant_id`` never returns the other tenant's rows."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_a = uuid7()
    tenant_b = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tenant_a, display_name="A", default_currency="INR"))
            db.add(Tenant(id=tenant_b, display_name="B", default_currency="INR"))
            db.add(
                EnquiryRow(
                    tenant_id=tenant_a,
                    created_by_user_id=uuid7(),
                    customer_name="Alpha Customer",
                )
            )
            db.add(
                EnquiryRow(
                    tenant_id=tenant_b,
                    created_by_user_id=uuid7(),
                    customer_name="Beta Customer",
                )
            )

    async with Session() as db:
        rows_a = (
            (
                await db.execute(
                    select(EnquiryRow).where(EnquiryRow.tenant_id == tenant_a)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows_a) == 1
        assert rows_a[0].customer_name == "Alpha Customer"

        rows_b = (
            (
                await db.execute(
                    select(EnquiryRow).where(EnquiryRow.tenant_id == tenant_b)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows_b) == 1
        assert rows_b[0].customer_name == "Beta Customer"


async def test_enquiry_compound_index_exists(engine: AsyncEngine) -> None:
    """The ``(tenant_id, status, created_at)`` listing index is created."""

    def _inspect(sync_conn):  # type: ignore[no-untyped-def]
        inspector = sa_inspect(sync_conn)
        return inspector.get_indexes("enquiries")

    async with engine.begin() as conn:
        indexes = await conn.run_sync(_inspect)

    names_to_columns = {ix["name"]: list(ix["column_names"]) for ix in indexes}
    assert "ix_enquiries_tenant_status_created" in names_to_columns
    assert names_to_columns["ix_enquiries_tenant_status_created"] == [
        "tenant_id",
        "status",
        "created_at",
    ]
