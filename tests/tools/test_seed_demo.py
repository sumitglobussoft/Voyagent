"""Tests for the demo-tenant seeder (``tools/seed_demo.py``).

The seeder is driven against an aiosqlite engine — the test passes the
engine directly via the ``engine=`` parameter so no environment
variables need to be set.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base
from schemas.storage.audit import AuditEventRow
from schemas.storage.enquiry import EnquiryRow
from schemas.storage.invoice import BillRow, InvoiceRow
from schemas.storage.ledger import JournalEntryRow, LedgerAccountRow
from schemas.storage.tenant import Tenant
from schemas.storage.user import User, UserRole

from tools import seed_demo


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def engine(tmp_path):
    db_path = tmp_path / "seed-demo-test.sqlite"
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        future=True,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def sm(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def _make_demo_user(sm) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with sm() as s:
        s.add(
            Tenant(
                id=tenant_id,
                display_name="Demo Tenant",
                default_currency="INR",
                is_active=True,
            )
        )
        await s.flush()
        s.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                external_id=f"demo-{user_id}",
                display_name="Demo User",
                email=seed_demo.DEMO_EMAIL,
                role=UserRole.AGENCY_ADMIN,
                email_verified=True,
            )
        )
        await s.commit()
    return tenant_id, user_id


async def _make_extra_user(sm, email: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with sm() as s:
        s.add(
            Tenant(
                id=tenant_id,
                display_name=f"Other {email}",
                default_currency="INR",
                is_active=True,
            )
        )
        await s.flush()
        s.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                external_id=f"x-{user_id}",
                display_name=f"Other {email}",
                email=email,
                role=UserRole.AGENCY_ADMIN,
                email_verified=True,
            )
        )
        await s.commit()
    return tenant_id, user_id


async def _count(sm, model, **filters) -> int:
    async with sm() as s:
        stmt = select(func.count()).select_from(model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        return int((await s.execute(stmt)).scalar_one())


# --------------------------------------------------------------------------- #


async def test_seed_demo_requires_demo_user_to_exist(engine) -> None:
    # DB is empty — no demo user.
    messages: list[str] = []
    rc = await seed_demo.main(engine=engine, print_fn=messages.append)
    assert rc == 1
    assert any("demo user not found" in m for m in messages)


async def test_seed_demo_first_run_creates_expected_row_counts(
    engine, sm
) -> None:
    tid, _ = await _make_demo_user(sm)
    rc = await seed_demo.main(engine=engine, print_fn=lambda _m: None)
    assert rc == 0

    assert await _count(sm, EnquiryRow, tenant_id=tid) == 5
    assert await _count(sm, InvoiceRow, tenant_id=tid) == 3
    assert await _count(sm, BillRow, tenant_id=tid) == 3
    assert await _count(sm, LedgerAccountRow, tenant_id=tid) == 5
    # Three balanced entries × 2 lines each = 6 journal_entry rows.
    assert await _count(sm, JournalEntryRow, tenant_id=tid) == 6
    # Three unique entry_ids.
    async with sm() as s:
        distinct_entries = (
            await s.execute(
                select(func.count(func.distinct(JournalEntryRow.entry_id)))
                .where(JournalEntryRow.tenant_id == tid)
            )
        ).scalar_one()
    assert distinct_entries == 3
    assert await _count(sm, AuditEventRow, tenant_id=tid) == 5


async def test_seed_demo_second_run_is_idempotent(engine, sm) -> None:
    tid, _ = await _make_demo_user(sm)
    assert await seed_demo.main(engine=engine, print_fn=lambda _m: None) == 0

    counts_before = {
        "enquiries": await _count(sm, EnquiryRow, tenant_id=tid),
        "invoices": await _count(sm, InvoiceRow, tenant_id=tid),
        "bills": await _count(sm, BillRow, tenant_id=tid),
        "accounts": await _count(sm, LedgerAccountRow, tenant_id=tid),
        "journal_entries": await _count(
            sm, JournalEntryRow, tenant_id=tid
        ),
        "audit_events": await _count(sm, AuditEventRow, tenant_id=tid),
    }
    messages: list[str] = []
    rc = await seed_demo.main(engine=engine, print_fn=messages.append)
    assert rc == 0
    assert any("already seeded" in m for m in messages)

    counts_after = {
        "enquiries": await _count(sm, EnquiryRow, tenant_id=tid),
        "invoices": await _count(sm, InvoiceRow, tenant_id=tid),
        "bills": await _count(sm, BillRow, tenant_id=tid),
        "accounts": await _count(sm, LedgerAccountRow, tenant_id=tid),
        "journal_entries": await _count(
            sm, JournalEntryRow, tenant_id=tid
        ),
        "audit_events": await _count(sm, AuditEventRow, tenant_id=tid),
    }
    assert counts_before == counts_after


async def test_seed_demo_dry_run_writes_nothing(engine, sm) -> None:
    tid, _ = await _make_demo_user(sm)
    messages: list[str] = []
    rc = await seed_demo.main(
        engine=engine, dry_run=True, print_fn=messages.append
    )
    assert rc == 0
    assert any("dry-run" in m for m in messages)
    assert await _count(sm, EnquiryRow, tenant_id=tid) == 0
    assert await _count(sm, InvoiceRow, tenant_id=tid) == 0
    assert await _count(sm, LedgerAccountRow, tenant_id=tid) == 0


async def test_seed_demo_only_touches_demo_tenant(engine, sm) -> None:
    demo_tid, _ = await _make_demo_user(sm)
    other_tid, _ = await _make_extra_user(sm, email="other@example.com")

    rc = await seed_demo.main(engine=engine, print_fn=lambda _m: None)
    assert rc == 0

    assert await _count(sm, EnquiryRow, tenant_id=demo_tid) == 5
    assert await _count(sm, EnquiryRow, tenant_id=other_tid) == 0
    assert await _count(sm, InvoiceRow, tenant_id=other_tid) == 0
    assert await _count(sm, LedgerAccountRow, tenant_id=other_tid) == 0
    assert await _count(sm, JournalEntryRow, tenant_id=other_tid) == 0


async def test_seed_demo_journal_entries_are_balanced(engine, sm) -> None:
    tid, _ = await _make_demo_user(sm)
    assert await seed_demo.main(engine=engine, print_fn=lambda _m: None) == 0

    async with sm() as s:
        rows = (
            await s.execute(
                select(
                    JournalEntryRow.entry_id,
                    func.sum(JournalEntryRow.debit),
                    func.sum(JournalEntryRow.credit),
                )
                .where(JournalEntryRow.tenant_id == tid)
                .group_by(JournalEntryRow.entry_id)
            )
        ).all()
    assert rows, "seeder produced no journal entries"
    for _eid, debit, credit in rows:
        assert debit == credit, f"unbalanced entry: {debit} vs {credit}"
