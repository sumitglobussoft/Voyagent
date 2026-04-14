"""Tests for the ledger write helper + account model."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import (
    JournalEntryRow,
    JournalLine,
    LedgerAccountRow,
    LedgerAccountTypeEnum,
    Tenant,
    UnbalancedJournalEntryError,
    build_journal_entry,
    uuid7,
)

pytestmark = pytest.mark.asyncio


async def _seed_accounts(engine: AsyncEngine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()
    ar_id = uuid7()
    rev_id = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tenant_id, display_name="Agency", default_currency="INR"))
            db.add(
                LedgerAccountRow(
                    id=ar_id,
                    tenant_id=tenant_id,
                    code="1200",
                    name="Accounts Receivable",
                    type=LedgerAccountTypeEnum.ASSET,
                )
            )
            db.add(
                LedgerAccountRow(
                    id=rev_id,
                    tenant_id=tenant_id,
                    code="4000",
                    name="Sales Revenue",
                    type=LedgerAccountTypeEnum.REVENUE,
                )
            )
    return Session, tenant_id, ar_id, rev_id


async def test_balanced_journal_entry_posts(engine: AsyncEngine) -> None:
    Session, tenant_id, ar_id, rev_id = await _seed_accounts(engine)

    rows = build_journal_entry(
        tenant_id=tenant_id,
        lines=[
            JournalLine(account_id=ar_id, debit=Decimal("1000.00")),
            JournalLine(account_id=rev_id, credit=Decimal("1000.00")),
        ],
        source="invoice:INV-1",
    )
    assert len(rows) == 2
    assert rows[0].entry_id == rows[1].entry_id

    async with Session() as db:
        async with db.begin():
            for row in rows:
                db.add(row)

    async with Session() as db:
        persisted = (
            (
                await db.execute(
                    select(JournalEntryRow).where(
                        JournalEntryRow.tenant_id == tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(persisted) == 2
        total_debit = sum(r.debit for r in persisted)
        total_credit = sum(r.credit for r in persisted)
        assert total_debit == total_credit == Decimal("1000.00")


async def test_unbalanced_entry_rejected(engine: AsyncEngine) -> None:
    _, tenant_id, ar_id, rev_id = await _seed_accounts(engine)
    with pytest.raises(UnbalancedJournalEntryError):
        build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(account_id=ar_id, debit=Decimal("1000.00")),
                JournalLine(account_id=rev_id, credit=Decimal("999.99")),
            ],
        )


async def test_single_line_entry_rejected(engine: AsyncEngine) -> None:
    _, tenant_id, ar_id, _ = await _seed_accounts(engine)
    with pytest.raises(UnbalancedJournalEntryError):
        build_journal_entry(
            tenant_id=tenant_id,
            lines=[JournalLine(account_id=ar_id, debit=Decimal("1.00"))],
        )


async def test_line_with_both_debit_and_credit_rejected(
    engine: AsyncEngine,
) -> None:
    _, tenant_id, ar_id, rev_id = await _seed_accounts(engine)
    with pytest.raises(UnbalancedJournalEntryError):
        build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(
                    account_id=ar_id,
                    debit=Decimal("5.00"),
                    credit=Decimal("5.00"),
                ),
                JournalLine(account_id=rev_id, credit=Decimal("10.00")),
            ],
        )


async def test_negative_amount_rejected(engine: AsyncEngine) -> None:
    _, tenant_id, ar_id, rev_id = await _seed_accounts(engine)
    with pytest.raises(UnbalancedJournalEntryError):
        build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(account_id=ar_id, debit=Decimal("-100.00")),
                JournalLine(account_id=rev_id, credit=Decimal("-100.00")),
            ],
        )
