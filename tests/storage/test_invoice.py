"""Round-trip + unique-constraint tests for :mod:`schemas.storage.invoice`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import (
    BillRow,
    BillStatusEnum,
    InvoiceRow,
    InvoiceStatusEnum,
    Tenant,
    uuid7,
)

pytestmark = pytest.mark.asyncio


async def test_invoice_round_trip_preserves_decimal(
    engine: AsyncEngine,
) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tenant_id, display_name="Acme", default_currency="INR"))
            db.add(
                InvoiceRow(
                    tenant_id=tenant_id,
                    number="INV-0001",
                    party_name="Acme Corp",
                    issue_date=date(2026, 4, 1),
                    due_date=date(2026, 5, 1),
                    total_amount=Decimal("12345.67"),
                    currency="INR",
                    amount_paid=Decimal("100.50"),
                    status=InvoiceStatusEnum.PARTIALLY_PAID,
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(InvoiceRow).where(InvoiceRow.number == "INV-0001")
            )
        ).scalar_one()
        # Decimals round-trip exactly.
        assert row.total_amount == Decimal("12345.67")
        assert row.amount_paid == Decimal("100.50")
        assert row.currency == "INR"
        assert row.status == InvoiceStatusEnum.PARTIALLY_PAID


async def test_invoice_number_unique_per_tenant(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_a = uuid7()
    tenant_b = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tenant_a, display_name="A", default_currency="INR"))
            db.add(Tenant(id=tenant_b, display_name="B", default_currency="INR"))
            # Same number across tenants — allowed.
            db.add(
                InvoiceRow(
                    tenant_id=tenant_a,
                    number="INV-1",
                    party_name="X",
                    issue_date=date(2026, 1, 1),
                    due_date=date(2026, 2, 1),
                    total_amount=Decimal("10.00"),
                    currency="INR",
                )
            )
            db.add(
                InvoiceRow(
                    tenant_id=tenant_b,
                    number="INV-1",
                    party_name="Y",
                    issue_date=date(2026, 1, 1),
                    due_date=date(2026, 2, 1),
                    total_amount=Decimal("20.00"),
                    currency="INR",
                )
            )

    # Same number repeated within the same tenant — must blow up.
    async with Session() as db:
        db.add(
            InvoiceRow(
                tenant_id=tenant_a,
                number="INV-1",
                party_name="X",
                issue_date=date(2026, 1, 1),
                due_date=date(2026, 2, 1),
                total_amount=Decimal("30.00"),
                currency="INR",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_bill_vendor_reference_unique_per_tenant(
    engine: AsyncEngine,
) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(
                Tenant(id=tenant_id, display_name="Agency", default_currency="INR")
            )
            db.add(
                BillRow(
                    tenant_id=tenant_id,
                    number="BILL-1",
                    vendor_reference="BSP-9000",
                    party_name="IATA BSP India",
                    issue_date=date(2026, 1, 1),
                    due_date=date(2026, 2, 1),
                    total_amount=Decimal("5000.00"),
                    currency="INR",
                    status=BillStatusEnum.RECEIVED,
                )
            )

    async with Session() as db:
        db.add(
            BillRow(
                tenant_id=tenant_id,
                number="BILL-2",  # different internal number …
                vendor_reference="BSP-9000",  # … but same supplier doc
                party_name="IATA BSP India",
                issue_date=date(2026, 1, 1),
                due_date=date(2026, 2, 1),
                total_amount=Decimal("5000.00"),
                currency="INR",
                status=BillStatusEnum.RECEIVED,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
