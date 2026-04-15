"""Accounting-domain tool handlers: list_ledger_accounts, post_journal_entry,
fetch_bsp_statement, reconcile_bsp.

These tests use stub drivers rather than real network clients. The stubs
satisfy the capability protocols via structural typing — they expose the
methods the tools call.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from drivers._contracts.errors import CapabilityNotSupportedError
from schemas.canonical import (
    AccountType,
    ActorKind,
    BSPReport,
    BSPTransaction,
    BSPTransactionKind,
    CountryCode,
    EntityId,
    LedgerAccount,
    LocalizedText,
    Money,
    Period,
    Ticket,
    TicketStatus,
)

from voyagent_agent_runtime.drivers import DriverRegistry
from voyagent_agent_runtime.tools import (
    BSP_REPORTS_CACHE_KEY,
    DRIVER_REGISTRY_KEY,
    InMemoryAuditSink,
    TICKETS_STORE_KEY,
    ToolContext,
    invoke_tool,
)


pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# Id helper                                                                   #
# --------------------------------------------------------------------------- #


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


# --------------------------------------------------------------------------- #
# Stubs                                                                       #
# --------------------------------------------------------------------------- #


class StubAccountingDriver:
    """Implements AccountingDriver structurally without any I/O."""

    name = "stub_accounting"
    version = "0.0.1"

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self.posted: list[Any] = []
        self.invoices: list[Any] = []
        self.read_balance_raises_not_supported = True

    def manifest(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def list_accounts(self) -> list[LedgerAccount]:
        now = datetime.now(timezone.utc)
        accounts: list[LedgerAccount] = []
        for code, name, kind in [
            ("1000", "Cash", AccountType.ASSET),
            ("1200", "Sundry Debtors", AccountType.ASSET),
            ("4000", "Sales - Domestic", AccountType.INCOME),
            ("5000", "Indirect Expenses", AccountType.EXPENSE),
        ]:
            accounts.append(
                LedgerAccount(
                    id=_uuid7_like(),
                    tenant_id=self._tenant_id,
                    code=code,
                    name=LocalizedText(default=name),
                    type=kind,
                    created_at=now,
                    updated_at=now,
                )
            )
        return accounts

    async def post_journal(self, entry: Any) -> str:
        self.posted.append(entry)
        return _uuid7_like()

    async def create_invoice(self, invoice: Any) -> str:  # pragma: no cover
        self.invoices.append(invoice)
        return _uuid7_like()

    async def read_invoice(self, invoice_id: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def read_account_balance(self, account_id: str, as_of: date) -> Money:
        if self.read_balance_raises_not_supported:
            raise CapabilityNotSupportedError(
                self.name, "stub does not implement read_account_balance"
            )
        return Money(amount=Decimal("1000.00"), currency="INR")

    async def aclose(self) -> None:
        return None


class StubBSPDriver:
    """Implements BSPDriver structurally."""

    name = "stub_bsp"
    version = "0.0.1"

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self.fetch_calls: list[tuple[str, Period]] = []

    def manifest(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def fetch_statement(self, country: CountryCode, period: Period) -> BSPReport:
        self.fetch_calls.append((country, period))
        now = datetime.now(timezone.utc)
        tx = BSPTransaction(
            kind=BSPTransactionKind.SALE,
            document_number="1761234567890",
            issue_date=date(2026, 4, 2),
            airline="6E",
            gross=Money(amount=Decimal("20000"), currency="INR"),
            commission=Money(amount=Decimal("1000"), currency="INR"),
            taxes=[],
            net=Money(amount=Decimal("18500"), currency="INR"),
        )
        return BSPReport(
            id=_uuid7_like(),
            tenant_id=self._tenant_id,
            country=country,
            period=period,
            airline=None,
            sales_total=Money(amount=Decimal("20000"), currency="INR"),
            refund_total=Money(amount=Decimal("0"), currency="INR"),
            commission_total=Money(amount=Decimal("1000"), currency="INR"),
            net_remittance=Money(amount=Decimal("18500"), currency="INR"),
            transactions=[tx],
            source_ref="stub-haf",
            created_at=now,
            updated_at=now,
        )

    async def raise_adm(self, reference: str, reason: Any) -> str:  # pragma: no cover
        raise CapabilityNotSupportedError(self.name, "n/a")

    async def raise_acm(self, reference: str, reason: Any) -> str:  # pragma: no cover
        raise CapabilityNotSupportedError(self.name, "n/a")

    async def make_settlement_payment(self, report_id: EntityId) -> Any:  # pragma: no cover
        raise CapabilityNotSupportedError(self.name, "n/a")

    async def aclose(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def stub_tenant_id() -> str:
    return _uuid7_like()


@pytest.fixture
def stub_accounting(stub_tenant_id: str) -> StubAccountingDriver:
    return StubAccountingDriver(tenant_id=stub_tenant_id)


@pytest.fixture
def stub_bsp(stub_tenant_id: str) -> StubBSPDriver:
    return StubBSPDriver(tenant_id=stub_tenant_id)


@pytest.fixture
def accounting_registry(
    stub_accounting: StubAccountingDriver, stub_bsp: StubBSPDriver
) -> DriverRegistry:
    reg = DriverRegistry()
    reg.register("AccountingDriver", stub_accounting)
    reg.register("BSPDriver", stub_bsp)
    return reg


@pytest.fixture
def accounting_ctx(
    stub_tenant_id: str, accounting_registry: DriverRegistry
) -> ToolContext:
    # contract changed — RBAC short-circuit now runs before the approval gate
    # (tools.py). Default role must satisfy approval_roles on post_journal_entry
    # / create_invoice so approval-gate tests see ``approval_needed`` first.
    return ToolContext(
        tenant_id=stub_tenant_id,
        actor_id=_uuid7_like(),
        actor_kind=ActorKind.HUMAN,
        session_id=_uuid7_like(),
        turn_id="t-acct-000001",
        actor_role="accountant",
        approvals={},
        extensions={DRIVER_REGISTRY_KEY: accounting_registry},
    )


# --------------------------------------------------------------------------- #
# list_ledger_accounts                                                        #
# --------------------------------------------------------------------------- #


async def test_list_ledger_accounts_returns_compact_rows(
    accounting_ctx: ToolContext,
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool("list_ledger_accounts", {}, accounting_ctx, audit_sink=sink)
    assert outcome.kind == "success"
    assert (outcome.output or {}).get("count") == 4
    rows = (outcome.output or {}).get("accounts")
    assert isinstance(rows, list) and rows
    for row in rows:
        assert set(row.keys()) == {"id", "code", "name", "type"}
    # No audit for read-only tools.
    assert sink.events == []


# --------------------------------------------------------------------------- #
# post_journal_entry — approval gate                                          #
# --------------------------------------------------------------------------- #


def _journal_input(account_ids: list[str]) -> dict[str, Any]:
    return {
        "entry": {
            "narration": "Daily cash sale",
            "entry_date": "2026-04-14",
            "lines": [
                {
                    "account_id": account_ids[0],
                    "debit_amount": "18500.00",
                    "currency": "INR",
                },
                {
                    "account_id": account_ids[1],
                    "credit_amount": "18500.00",
                    "currency": "INR",
                },
            ],
        }
    }


async def test_post_journal_entry_first_call_requests_approval(
    accounting_ctx: ToolContext, stub_accounting: StubAccountingDriver
) -> None:
    sink = InMemoryAuditSink()
    accounts = await stub_accounting.list_accounts()
    ids = [a.id for a in accounts[:2]]
    outcome = await invoke_tool(
        "post_journal_entry", _journal_input(ids), accounting_ctx, audit_sink=sink
    )
    assert outcome.kind == "approval_needed"
    assert outcome.approval_id and outcome.approval_id.startswith("ap-")
    assert sink.events == []


async def test_post_journal_entry_after_approval_posts_and_audits(
    accounting_ctx: ToolContext, stub_accounting: StubAccountingDriver
) -> None:
    sink = InMemoryAuditSink()
    accounts = await stub_accounting.list_accounts()
    ids = [a.id for a in accounts[:2]]
    first = await invoke_tool(
        "post_journal_entry", _journal_input(ids), accounting_ctx, audit_sink=sink
    )
    accounting_ctx.approvals = {first.approval_id: True}
    second = await invoke_tool(
        "post_journal_entry", _journal_input(ids), accounting_ctx, audit_sink=sink
    )
    assert second.kind == "success"
    assert (second.output or {}).get("posted") is True
    assert (second.output or {}).get("journal_id")
    # Two audit events: STARTED + SUCCEEDED.
    assert len(sink.events) == 2
    # Driver observed the post.
    assert len(stub_accounting.posted) == 1


# --------------------------------------------------------------------------- #
# fetch_bsp_statement                                                         #
# --------------------------------------------------------------------------- #


async def test_fetch_bsp_statement_caches_report(
    accounting_ctx: ToolContext, stub_bsp: StubBSPDriver
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "fetch_bsp_statement",
        {
            "country": "IN",
            "period_start": "2026-04-01",
            "period_end": "2026-04-15",
        },
        accounting_ctx,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    out = outcome.output or {}
    assert out["country"] == "IN"
    assert out["report_id"]
    assert out["transaction_count"] == 1
    # Report cached for later reconcile_bsp calls.
    cache = accounting_ctx.extensions.get(BSP_REPORTS_CACHE_KEY)
    assert isinstance(cache, dict)
    assert out["report_id"] in cache


# --------------------------------------------------------------------------- #
# reconcile_bsp                                                               #
# --------------------------------------------------------------------------- #


async def test_reconcile_bsp_reports_match_for_matching_internal_ticket(
    accounting_ctx: ToolContext, stub_tenant_id: str
) -> None:
    sink = InMemoryAuditSink()
    # First populate the cache.
    fetched = await invoke_tool(
        "fetch_bsp_statement",
        {
            "country": "IN",
            "period_start": "2026-04-01",
            "period_end": "2026-04-15",
        },
        accounting_ctx,
        audit_sink=sink,
    )
    report_id = (fetched.output or {}).get("report_id")
    assert report_id

    # Seed tickets store with a matching internal ticket.
    now = datetime.now(timezone.utc)
    t = Ticket(
        id=_uuid7_like(),
        tenant_id=stub_tenant_id,
        number="1761234567890",
        pnr_id=_uuid7_like(),
        passenger_id=_uuid7_like(),
        issued_at=now,
        issuing_airline="6E",
        base_amount=Money(amount=Decimal("17500"), currency="INR"),
        tax_amount=Money(amount=Decimal("1000"), currency="INR"),
        total_amount=Money(amount=Decimal("18500"), currency="INR"),
        status=TicketStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    accounting_ctx.extensions[TICKETS_STORE_KEY] = {t.id: t}

    outcome = await invoke_tool(
        "reconcile_bsp",
        {"report_id": report_id},
        accounting_ctx,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    out = outcome.output or {}
    assert out["reconciled"] is True
    assert out["summary"]["matched"] == 1
    # The matched row is filtered out of issues.
    assert all(i["outcome"] != "matched" for i in out["issues"])


async def test_reconcile_bsp_reports_not_found_when_cache_miss(
    accounting_ctx: ToolContext,
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "reconcile_bsp",
        {"report_id": _uuid7_like()},
        accounting_ctx,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    out = outcome.output or {}
    assert out["reconciled"] is False
    assert out["reason"] == "report_not_found"


# --------------------------------------------------------------------------- #
# read_account_balance — surfaces capability-not-supported                    #
# --------------------------------------------------------------------------- #


async def test_read_account_balance_surfaces_not_supported_cleanly(
    accounting_ctx: ToolContext,
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "read_account_balance",
        {"account_id": _uuid7_like(), "as_of": "2026-04-14"},
        accounting_ctx,
        audit_sink=sink,
    )
    assert outcome.kind == "success"  # handler returned structurally, no raise
    out = outcome.output or {}
    assert out["read"] is False
    assert out["reason"] == "capability_not_supported"
