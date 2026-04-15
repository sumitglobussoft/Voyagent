"""Tests for the ``draft_invoice`` accounting tool.

These tests wire a real aiosqlite engine onto ``ctx.extensions`` via
:data:`voyagent_agent_runtime.tools.DB_SESSIONMAKER_KEY` so the tool
exercises its full read+write path without touching Postgres.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from schemas.canonical import ActorKind
from schemas.storage import Base
from schemas.storage.invoice import InvoiceRow, InvoiceStatusEnum

from voyagent_agent_runtime.tools import (
    DB_SESSIONMAKER_KEY,
    InMemoryAuditSink,
    ToolContext,
    invoke_tool,
)


pytestmark = pytest.mark.asyncio


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


@pytest.fixture
async def sm(tmp_path):
    # A tmp-file SQLite DB to side-step the aiosqlite+StaticPool race
    # that the /api/approvals tests hit with in-memory DBs.
    db_path = tmp_path / "draft-invoice-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


def _make_ctx(tenant_id: str, sm: Any) -> ToolContext:
    return ToolContext(
        tenant_id=tenant_id,
        actor_id=_uuid7_like(),
        actor_kind=ActorKind.HUMAN,
        session_id=_uuid7_like(),
        turn_id="t-draftinv-001",
        actor_role="accountant",
        approvals={},
        extensions={DB_SESSIONMAKER_KEY: sm},
    )


def _good_input(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "customer_name": "Alice Sharma",
        "issue_date": "2026-04-14",
        "due_date": "2026-05-14",
        "line_items": [
            {
                "description": "Air ticket BOM-DXB",
                "quantity": 1,
                "unit_price": "50000.00",
                "currency": "INR",
            },
            {
                "description": "Hotel 5 nights",
                "quantity": 5,
                "unit_price": "5000.00",
                "currency": "INR",
            },
        ],
    }
    base.update(overrides)
    return base


async def _invoke_with_approval(
    tool_input: dict[str, Any], ctx: ToolContext
) -> Any:
    sink = InMemoryAuditSink()
    first = await invoke_tool("draft_invoice", tool_input, ctx, audit_sink=sink)
    assert first.kind == "approval_needed"
    ctx.approvals = {first.approval_id: True}
    return await invoke_tool("draft_invoice", tool_input, ctx, audit_sink=sink)


async def test_draft_invoice_first_call_requires_approval(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "draft_invoice", _good_input(), ctx, audit_sink=sink
    )
    assert outcome.kind == "approval_needed"
    assert outcome.approval_id
    # No row written yet.
    async with sm() as s:
        rows = (await s.execute(select(InvoiceRow))).scalars().all()
    assert rows == []


async def test_draft_invoice_after_approval_writes_row_and_returns_output(
    sm,
) -> None:
    tid = _uuid7_like()
    ctx = _make_ctx(tid, sm)
    outcome = await _invoke_with_approval(_good_input(), ctx)
    assert outcome.kind == "success", outcome.error_message
    out = outcome.output or {}
    assert out["drafted"] is True
    assert out["status"] == "draft"
    assert out["currency"] == "INR"
    assert out["total_amount"] == "75000.00"
    assert out["invoice_id"]
    assert out["number"]

    async with sm() as s:
        rows = (await s.execute(select(InvoiceRow))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert str(row.tenant_id) == tid
    assert row.status == InvoiceStatusEnum.DRAFT
    assert row.total_amount == Decimal("75000.00")
    assert row.number == out["number"]
    assert row.party_name == "Alice Sharma"


async def test_draft_invoice_total_is_sum_of_line_items(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    tool_input = _good_input(
        line_items=[
            {
                "description": "A",
                "quantity": 2,
                "unit_price": "100.00",
                "currency": "INR",
            },
            {
                "description": "B",
                "quantity": 3,
                "unit_price": "250.50",
                "currency": "INR",
            },
            {
                "description": "C",
                "quantity": 1,
                "unit_price": "49.49",
                "currency": "INR",
            },
        ]
    )
    outcome = await _invoke_with_approval(tool_input, ctx)
    assert outcome.kind == "success"
    # 2*100 + 3*250.50 + 1*49.49 = 200 + 751.50 + 49.49 = 1000.99
    expected = Decimal("200.00") + Decimal("751.50") + Decimal("49.49")
    assert (outcome.output or {})["total_amount"] == str(expected)


async def test_draft_invoice_mixed_currency_returns_error(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    tool_input = _good_input(
        line_items=[
            {
                "description": "INR leg",
                "quantity": 1,
                "unit_price": "100.00",
                "currency": "INR",
            },
            {
                "description": "USD leg",
                "quantity": 1,
                "unit_price": "5.00",
                "currency": "USD",
            },
        ]
    )
    # Needs approval first so the handler actually runs.
    outcome = await _invoke_with_approval(tool_input, ctx)
    assert outcome.kind == "success"  # structured error
    out = outcome.output or {}
    assert out["drafted"] is False
    assert out["error_code"] == "mixed_currency"
    async with sm() as s:
        rows = (await s.execute(select(InvoiceRow))).scalars().all()
    assert rows == []


async def test_draft_invoice_auto_generates_number_when_omitted(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    outcome = await _invoke_with_approval(_good_input(), ctx)
    assert outcome.kind == "success"
    number = (outcome.output or {})["number"]
    assert re.match(r"^INV-[A-Z0-9]{8}-\d{4}$", number), number
    async with sm() as s:
        stored = (await s.execute(select(InvoiceRow.number))).scalar_one()
    assert stored == number


async def test_draft_invoice_auto_generated_number_increments_per_tenant(
    sm,
) -> None:
    tid_a = _uuid7_like()
    tid_b = _uuid7_like()

    ctx_a = _make_ctx(tid_a, sm)
    numbers_a: list[str] = []
    for i in range(3):
        # Each call is a fresh turn so the approval-id differs.
        ctx_a.turn_id = f"t-a-{i}"
        ctx_a.approvals = {}
        outcome = await _invoke_with_approval(_good_input(), ctx_a)
        assert outcome.kind == "success"
        numbers_a.append((outcome.output or {})["number"])

    assert len(numbers_a) == 3
    seqs = [int(n.rsplit("-", 1)[1]) for n in numbers_a]
    assert seqs == [1, 2, 3]

    ctx_b = _make_ctx(tid_b, sm)
    ctx_b.turn_id = "t-b-0"
    outcome_b = await _invoke_with_approval(_good_input(), ctx_b)
    assert outcome_b.kind == "success"
    nb = (outcome_b.output or {})["number"]
    assert nb.endswith("-0001")


async def test_draft_invoice_with_explicit_number_that_already_exists_returns_error(
    sm,
) -> None:
    tid = _uuid7_like()
    # Pre-insert a row using the same table.
    async with sm() as s:
        s.add(
            InvoiceRow(
                tenant_id=uuid.UUID(tid),
                number="INV-TEST",
                party_name="Existing",
                issue_date=__import__("datetime").date(2026, 1, 1),
                due_date=__import__("datetime").date(2026, 2, 1),
                total_amount=Decimal("10.00"),
                currency="INR",
                amount_paid=Decimal("0.00"),
                status=InvoiceStatusEnum.ISSUED,
            )
        )
        await s.commit()

    ctx = _make_ctx(tid, sm)
    outcome = await _invoke_with_approval(
        _good_input(number="INV-TEST"), ctx
    )
    assert outcome.kind == "success"
    out = outcome.output or {}
    assert out["drafted"] is False
    assert out["error_code"] == "invoice_number_conflict"


async def test_draft_invoice_tenant_isolation(sm) -> None:
    tid_a = _uuid7_like()
    tid_b = _uuid7_like()
    ctx_a = _make_ctx(tid_a, sm)
    outcome = await _invoke_with_approval(_good_input(), ctx_a)
    assert outcome.kind == "success"

    async with sm() as s:
        b_rows = (
            await s.execute(
                select(InvoiceRow).where(
                    InvoiceRow.tenant_id == uuid.UUID(tid_b)
                )
            )
        ).scalars().all()
    assert b_rows == []


async def test_draft_invoice_uses_decimal_never_float(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    tool_input = _good_input(
        line_items=[
            {
                "description": "Precise price",
                "quantity": 1,
                "unit_price": "12345.67",
                "currency": "INR",
            }
        ]
    )
    outcome = await _invoke_with_approval(tool_input, ctx)
    assert outcome.kind == "success"
    async with sm() as s:
        row = (await s.execute(select(InvoiceRow))).scalar_one()
    # Exact decimal, no float drift.
    assert row.total_amount == Decimal("12345.67")
    assert isinstance(row.total_amount, Decimal)


async def test_draft_invoice_rejects_zero_quantity(sm) -> None:
    ctx = _make_ctx(_uuid7_like(), sm)
    sink = InMemoryAuditSink()
    bad = _good_input(
        line_items=[
            {
                "description": "Zero qty",
                "quantity": 0,
                "unit_price": "100.00",
                "currency": "INR",
            }
        ]
    )
    outcome = await invoke_tool("draft_invoice", bad, ctx, audit_sink=sink)
    assert outcome.kind == "error"
    assert "validation" in (outcome.error_message or "").lower()
    async with sm() as s:
        rows = (await s.execute(select(InvoiceRow))).scalars().all()
    assert rows == []
