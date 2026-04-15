"""Seed the demo tenant with realistic sample data.

Run:
    python tools/seed_demo.py              # seeds prod via .env.prod
    python tools/seed_demo.py --dry-run    # reports what would be seeded

Idempotent — safe to run multiple times. On second invocation the
seeder finds the marker enquiry (Alice Sharma) and exits 0 without
touching the DB.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from schemas.canonical import ActorKind
from schemas.storage.audit import AuditEventRow, AuditStatusEnum
from schemas.storage.enquiry import EnquiryRow, EnquiryStatusEnum
from schemas.storage.invoice import (
    BillRow,
    BillStatusEnum,
    InvoiceRow,
    InvoiceStatusEnum,
)
from schemas.storage.ledger import (
    JournalEntryRow,
    JournalLine,
    LedgerAccountRow,
    LedgerAccountTypeEnum,
    build_journal_entry,
)
from schemas.storage.session import ActorKindEnum
from schemas.storage.user import User


DEMO_EMAIL = "demo@voyagent.globusdemos.com"
DEMO_MARKER_CUSTOMER = "[DEMO SEED] Alice Sharma"


ENQUIRIES: list[dict[str, Any]] = [
    {
        "customer_name": DEMO_MARKER_CUSTOMER,
        "origin": "BOM",
        "destination": "DXB",
        "pax_count": 2,
        "budget_amount": Decimal("75000.00"),
        "status": EnquiryStatusEnum.NEW,
        "notes": "5 nights",
    },
    {
        "customer_name": "[DEMO SEED] Rahul Mehta",
        "origin": "DEL",
        "destination": "BKK",
        "pax_count": 2,
        "budget_amount": Decimal("90000.00"),
        "status": EnquiryStatusEnum.QUOTED,
        "notes": "6 nights",
    },
    {
        "customer_name": "[DEMO SEED] Priya Nair",
        "origin": "MAA",
        "destination": "SIN",
        "pax_count": 1,
        "budget_amount": Decimal("55000.00"),
        "status": EnquiryStatusEnum.BOOKED,
        "notes": "4 nights",
    },
    {
        "customer_name": "[DEMO SEED] Vikram Shah",
        "origin": "BLR",
        "destination": "LON",
        "pax_count": 2,
        "budget_amount": Decimal("180000.00"),
        "status": EnquiryStatusEnum.NEW,
        "notes": "8 nights",
    },
    {
        "customer_name": "[DEMO SEED] Deepa Iyer",
        "origin": "HYD",
        "destination": "KUL",
        "pax_count": 1,
        "budget_amount": Decimal("40000.00"),
        "status": EnquiryStatusEnum.CANCELLED,
        "notes": "3 nights",
    },
]


LEDGER_ACCOUNTS: list[tuple[str, str, LedgerAccountTypeEnum]] = [
    ("1000", "Cash", LedgerAccountTypeEnum.ASSET),
    ("1200", "Accounts Receivable", LedgerAccountTypeEnum.ASSET),
    ("2100", "Accounts Payable", LedgerAccountTypeEnum.LIABILITY),
    ("4000", "Sales Revenue", LedgerAccountTypeEnum.REVENUE),
    ("2200", "BSP Clearing", LedgerAccountTypeEnum.LIABILITY),
]


async def _resolve_demo_tenant(
    sessionmaker: async_sessionmaker,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Return ``(tenant_id, user_id)`` for the demo user.

    Direct SQL on ``users.email`` — the API does not currently expose a
    lookup for "what tenant does this email belong to", and the seeder
    is a local admin tool that already has DB creds.
    """
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(User.id, User.tenant_id).where(User.email == DEMO_EMAIL)
            )
        ).one_or_none()
    if row is None:
        raise RuntimeError(
            f"demo user not found (email={DEMO_EMAIL!r}). Create the demo "
            f"user via the auth sign-up endpoint before running the seeder."
        )
    return (row.tenant_id, row.id)


async def _already_seeded(
    sessionmaker: async_sessionmaker, tenant_id: uuid.UUID
) -> bool:
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(EnquiryRow.id).where(
                    EnquiryRow.tenant_id == tenant_id,
                    EnquiryRow.customer_name == DEMO_MARKER_CUSTOMER,
                )
            )
        ).first()
    return row is not None


async def _seed(
    sessionmaker: async_sessionmaker,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)

    async with sessionmaker() as s:
        # --- enquiries ---
        for e in ENQUIRIES:
            s.add(
                EnquiryRow(
                    tenant_id=tenant_id,
                    created_by_user_id=user_id,
                    customer_name=e["customer_name"],
                    origin=e["origin"],
                    destination=e["destination"],
                    depart_date=today + timedelta(days=30),
                    return_date=today + timedelta(days=35),
                    pax_count=e["pax_count"],
                    budget_amount=e["budget_amount"],
                    budget_currency="INR",
                    status=e["status"],
                    notes=e["notes"],
                )
            )

        # --- invoices ---
        invoices: list[dict[str, Any]] = [
            {
                "number": "INV-DEMO-0001",
                "party_name": "[DEMO SEED] Alice Sharma",
                "total": Decimal("75000.00"),
                "paid": Decimal("0.00"),
                "status": InvoiceStatusEnum.ISSUED,
            },
            {
                "number": "INV-DEMO-0002",
                "party_name": "[DEMO SEED] Rahul Mehta",
                "total": Decimal("90000.00"),
                "paid": Decimal("0.00"),
                "status": InvoiceStatusEnum.DRAFT,
            },
            {
                "number": "INV-DEMO-0003",
                "party_name": "[DEMO SEED] Priya Nair",
                "total": Decimal("55000.00"),
                "paid": Decimal("55000.00"),
                "status": InvoiceStatusEnum.PAID,
            },
        ]
        for inv in invoices:
            s.add(
                InvoiceRow(
                    tenant_id=tenant_id,
                    number=inv["number"],
                    party_name=inv["party_name"],
                    issue_date=today,
                    due_date=today + timedelta(days=30),
                    total_amount=inv["total"],
                    amount_paid=inv["paid"],
                    currency="INR",
                    status=inv["status"],
                )
            )

        # --- bills ---
        bills: list[dict[str, Any]] = [
            {
                "number": "BILL-DEMO-0001",
                "vendor_reference": "BSP-MAR-2026",
                "party_name": "BSP India March Settlement",
                "total": Decimal("45000.00"),
                "paid": Decimal("0.00"),
                "status": BillStatusEnum.RECEIVED,
            },
            {
                "number": "BILL-DEMO-0002",
                "vendor_reference": "HB-DUB-MAR",
                "party_name": "Hotelbeds - Dubai Marina",
                "total": Decimal("22000.00"),
                "paid": Decimal("0.00"),
                "status": BillStatusEnum.SCHEDULED,
            },
            {
                "number": "BILL-DEMO-0003",
                "vendor_reference": "VISA-IN-FEE-0003",
                "party_name": "Visa India agency fee",
                "total": Decimal("3500.00"),
                "paid": Decimal("3500.00"),
                "status": BillStatusEnum.PAID,
            },
        ]
        for b in bills:
            s.add(
                BillRow(
                    tenant_id=tenant_id,
                    number=b["number"],
                    vendor_reference=b["vendor_reference"],
                    party_name=b["party_name"],
                    issue_date=today,
                    due_date=today + timedelta(days=15),
                    total_amount=b["total"],
                    amount_paid=b["paid"],
                    currency="INR",
                    status=b["status"],
                )
            )

        # --- ledger accounts ---
        account_ids: dict[str, uuid.UUID] = {}
        for code, name, type_ in LEDGER_ACCOUNTS:
            existing_id = (
                await s.execute(
                    select(LedgerAccountRow.id).where(
                        LedgerAccountRow.tenant_id == tenant_id,
                        LedgerAccountRow.code == code,
                    )
                )
            ).scalar_one_or_none()
            if existing_id is not None:
                account_ids[code] = existing_id
                continue
            row = LedgerAccountRow(
                tenant_id=tenant_id,
                code=code,
                name=name,
                type=type_,
            )
            s.add(row)
            await s.flush()
            account_ids[code] = row.id

        # --- journal entries (balanced) ---
        # 1) Dr 1200 AR 75000, Cr 4000 Sales 75000
        for row in build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(
                    account_id=account_ids["1200"],
                    debit=Decimal("75000.00"),
                ),
                JournalLine(
                    account_id=account_ids["4000"],
                    credit=Decimal("75000.00"),
                ),
            ],
            source="demo-seed:invoice_0001",
        ):
            s.add(row)
        # 2) Dr 1000 Cash 55000, Cr 1200 AR 55000
        for row in build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(
                    account_id=account_ids["1000"],
                    debit=Decimal("55000.00"),
                ),
                JournalLine(
                    account_id=account_ids["1200"],
                    credit=Decimal("55000.00"),
                ),
            ],
            source="demo-seed:invoice_0003_paid",
        ):
            s.add(row)
        # 3) Dr 2100 AP 3500, Cr 1000 Cash 3500
        for row in build_journal_entry(
            tenant_id=tenant_id,
            lines=[
                JournalLine(
                    account_id=account_ids["2100"],
                    debit=Decimal("3500.00"),
                ),
                JournalLine(
                    account_id=account_ids["1000"],
                    credit=Decimal("3500.00"),
                ),
            ],
            source="demo-seed:visa_bill_paid",
        ):
            s.add(row)

        # --- audit events ---
        audit_events: list[tuple[str, AuditStatusEnum, datetime]] = [
            (
                "auth.verify",
                AuditStatusEnum.SUCCEEDED,
                now - timedelta(hours=1),
            ),
            (
                "auth.verify",
                AuditStatusEnum.SUCCEEDED,
                now - timedelta(minutes=10),
            ),
            (
                "approval.granted",
                AuditStatusEnum.SUCCEEDED,
                now - timedelta(minutes=8),
            ),
            (
                "approval.rejected",
                AuditStatusEnum.REJECTED,
                now - timedelta(minutes=5),
            ),
            (
                "tool.draft_invoice",
                AuditStatusEnum.SUCCEEDED,
                now - timedelta(minutes=2),
            ),
        ]
        for tool_name, status, started_at in audit_events:
            s.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    actor_kind=ActorKindEnum.HUMAN,
                    tool=tool_name,
                    entity_refs={},
                    inputs={},
                    outputs={},
                    approval_required=(tool_name.startswith("approval.")),
                    started_at=started_at,
                    completed_at=started_at,
                    status=status,
                )
            )

        await s.commit()


async def main(
    db_url: str | None = None,
    *,
    dry_run: bool = False,
    engine: AsyncEngine | None = None,
    print_fn=print,
) -> int:
    """Entry point for the seeder.

    Accepts an explicit ``engine`` parameter so tests can drive the
    seeder against their aiosqlite engine without monkey-patching env
    vars. In production the caller passes ``db_url`` (or leaves it
    blank and we read ``VOYAGENT_DB_URL``).
    """
    owned_engine = False
    if engine is None:
        url = db_url or os.environ.get("VOYAGENT_DB_URL")
        if not url:
            print_fn("error: VOYAGENT_DB_URL not set and no db_url provided.")
            return 2
        engine = create_async_engine(url, future=True)
        owned_engine = True
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        try:
            tenant_id, user_id = await _resolve_demo_tenant(sessionmaker)
        except RuntimeError as exc:
            print_fn(f"error: {exc}")
            return 1

        if await _already_seeded(sessionmaker, tenant_id):
            print_fn(
                f"demo tenant {tenant_id} already seeded — nothing to do."
            )
            return 0

        if dry_run:
            print_fn(
                f"dry-run: would seed demo tenant {tenant_id} with "
                f"{len(ENQUIRIES)} enquiries, 3 invoices, 3 bills, "
                f"{len(LEDGER_ACCOUNTS)} ledger accounts, 3 journal "
                f"entries, 5 audit events."
            )
            return 0

        await _seed(sessionmaker, tenant_id, user_id)
        print_fn(f"demo tenant {tenant_id} seeded.")
        return 0
    finally:
        if owned_engine:
            await engine.dispose()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--db-url",
        default=None,
        help="Optional DB URL override (defaults to VOYAGENT_DB_URL).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    ns = _parse_args()
    sys.exit(asyncio.run(main(db_url=ns.db_url, dry_run=ns.dry_run)))
