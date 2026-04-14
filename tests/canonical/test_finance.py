"""Tests for schemas.canonical.finance.

Covers Invoice / InvoiceLine currency consistency, JournalLine's
exactly-one-side invariant, JournalEntry per-currency balancing, and basic
Reconciliation construction.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

import pytest
from pydantic import ValidationError

from schemas.canonical import (
    Address,
    BSPTransaction,
    BSPTransactionKind,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LocalizedText,
    Money,
    Period,
    Reconciliation,
    ReconciliationScope,
    ReconciliationSummary,
    TaxLine,
    TaxRegime,
)


# --------------------------------------------------------------------------- #
# InvoiceLine                                                                 #
# --------------------------------------------------------------------------- #


class TestInvoiceLine:
    def test_invoice_line_all_amounts_share_currency(self) -> None:
        line = InvoiceLine(
            description="Ticket BLR-DXB",
            quantity=Decimal("1"),
            unit_price=Money(amount=Decimal("10000"), currency="INR"),
            subtotal=Money(amount=Decimal("10000"), currency="INR"),
            taxes=[
                TaxLine(
                    regime=TaxRegime.GST_INDIA,
                    code="IGST",
                    rate_bps=1800,
                    taxable_amount=Money(amount=Decimal("10000"), currency="INR"),
                    tax_amount=Money(amount=Decimal("1800"), currency="INR"),
                ),
            ],
            total=Money(amount=Decimal("11800"), currency="INR"),
        )
        assert line.total.currency == "INR"

    def test_invoice_line_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            InvoiceLine(
                description="Mismatch",
                unit_price=Money(amount=Decimal("100"), currency="INR"),
                subtotal=Money(amount=Decimal("100"), currency="USD"),
                total=Money(amount=Decimal("100"), currency="INR"),
            )

    def test_invoice_line_tax_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            InvoiceLine(
                description="Tax mismatch",
                unit_price=Money(amount=Decimal("100"), currency="INR"),
                subtotal=Money(amount=Decimal("100"), currency="INR"),
                taxes=[
                    TaxLine(
                        regime=TaxRegime.VAT_UAE,
                        code="VAT",
                        rate_bps=500,
                        taxable_amount=Money(amount=Decimal("100"), currency="AED"),
                        tax_amount=Money(amount=Decimal("5"), currency="AED"),
                    ),
                ],
                total=Money(amount=Decimal("105"), currency="INR"),
            )


# --------------------------------------------------------------------------- #
# Invoice                                                                     #
# --------------------------------------------------------------------------- #


def _valid_invoice_line() -> InvoiceLine:
    return InvoiceLine(
        description="Ticket",
        unit_price=Money(amount=Decimal("10000"), currency="INR"),
        subtotal=Money(amount=Decimal("10000"), currency="INR"),
        total=Money(amount=Decimal("10000"), currency="INR"),
    )


def _valid_billing_address() -> Address:
    return Address(country="IN", line1="1 Example Lane", city="Mumbai")


def _base_invoice_kwargs(make_entity_id: Callable[[], str]) -> dict:
    now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    return dict(
        id=make_entity_id(),
        tenant_id=make_entity_id(),
        created_at=now,
        updated_at=now,
        invoice_number="INV-2026-0001",
        client_id=make_entity_id(),
        issue_date=date(2026, 4, 14),
        currency="INR",
        lines=[_valid_invoice_line()],
        subtotal=Money(amount=Decimal("10000"), currency="INR"),
        tax_total=Money(amount=Decimal("0"), currency="INR"),
        grand_total=Money(amount=Decimal("10000"), currency="INR"),
        billing_address=_valid_billing_address(),
    )


class TestInvoiceCurrencyConsistency:
    def test_invoice_with_consistent_currency_is_valid(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        inv = Invoice(**_base_invoice_kwargs(make_entity_id))
        assert inv.currency == "INR"

    def test_invoice_subtotal_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        kwargs = _base_invoice_kwargs(make_entity_id)
        kwargs["subtotal"] = Money(amount=Decimal("10000"), currency="USD")
        with pytest.raises(ValidationError, match="Invoice totals must match"):
            Invoice(**kwargs)

    def test_invoice_tax_total_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        kwargs = _base_invoice_kwargs(make_entity_id)
        kwargs["tax_total"] = Money(amount=Decimal("0"), currency="AED")
        with pytest.raises(ValidationError, match="Invoice totals must match"):
            Invoice(**kwargs)

    def test_invoice_grand_total_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        kwargs = _base_invoice_kwargs(make_entity_id)
        kwargs["grand_total"] = Money(amount=Decimal("10000"), currency="GBP")
        with pytest.raises(ValidationError, match="Invoice totals must match"):
            Invoice(**kwargs)

    def test_invoice_line_currency_mismatch_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        kwargs = _base_invoice_kwargs(make_entity_id)
        kwargs["lines"] = [
            InvoiceLine(
                description="Foreign ticket",
                unit_price=Money(amount=Decimal("120"), currency="USD"),
                subtotal=Money(amount=Decimal("120"), currency="USD"),
                total=Money(amount=Decimal("120"), currency="USD"),
            )
        ]
        with pytest.raises(ValidationError, match="must match invoice currency"):
            Invoice(**kwargs)


# --------------------------------------------------------------------------- #
# JournalLine                                                                 #
# --------------------------------------------------------------------------- #


class TestJournalLine:
    def test_debit_only_is_valid(self, make_entity_id: Callable[[], str]) -> None:
        line = JournalLine(
            account_id=make_entity_id(),
            debit=Money(amount=Decimal("500"), currency="INR"),
        )
        assert line.debit is not None
        assert line.credit is None

    def test_credit_only_is_valid(self, make_entity_id: Callable[[], str]) -> None:
        line = JournalLine(
            account_id=make_entity_id(),
            credit=Money(amount=Decimal("500"), currency="INR"),
        )
        assert line.credit is not None
        assert line.debit is None

    def test_both_debit_and_credit_raises(self, make_entity_id: Callable[[], str]) -> None:
        with pytest.raises(ValidationError, match="exactly one of debit / credit"):
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("500"), currency="INR"),
                credit=Money(amount=Decimal("500"), currency="INR"),
            )

    def test_neither_debit_nor_credit_raises(self, make_entity_id: Callable[[], str]) -> None:
        with pytest.raises(ValidationError, match="exactly one of debit / credit"):
            JournalLine(account_id=make_entity_id())


# --------------------------------------------------------------------------- #
# JournalEntry                                                                #
# --------------------------------------------------------------------------- #


def _journal_entry_kwargs(
    make_entity_id: Callable[[], str],
    lines: list[JournalLine],
) -> dict:
    now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    return dict(
        id=make_entity_id(),
        tenant_id=make_entity_id(),
        created_at=now,
        updated_at=now,
        entry_date=date(2026, 4, 14),
        narration=LocalizedText(default="Sale of ticket"),
        lines=lines,
        source_event="invoice.issued",
    )


class TestJournalEntryBalancing:
    def test_balanced_single_currency_entry_is_valid(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        lines = [
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("1000"), currency="INR"),
            ),
        ]
        entry = JournalEntry(**_journal_entry_kwargs(make_entity_id, lines))
        assert len(entry.lines) == 2

    def test_unbalanced_single_currency_entry_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        lines = [
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("900"), currency="INR"),
            ),
        ]
        with pytest.raises(ValidationError, match="not balanced in INR"):
            JournalEntry(**_journal_entry_kwargs(make_entity_id, lines))

    def test_multi_currency_entry_balances_each_currency_independently(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        # INR side balances, USD side balances — this is the shape of an FX
        # gain/loss or intra-tenant transfer entry.
        lines = [
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("12"), currency="USD"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("12"), currency="USD"),
            ),
        ]
        entry = JournalEntry(**_journal_entry_kwargs(make_entity_id, lines))
        assert len(entry.lines) == 4

    def test_multi_currency_entry_one_currency_unbalanced_raises(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        # INR balances but USD does not — must raise, naming the offending currency.
        lines = [
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("12"), currency="USD"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("11"), currency="USD"),
            ),
        ]
        with pytest.raises(ValidationError, match="not balanced in USD"):
            JournalEntry(**_journal_entry_kwargs(make_entity_id, lines))

    def test_unbalanced_error_message_names_net_amount(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        lines = [
            JournalLine(
                account_id=make_entity_id(),
                debit=Money(amount=Decimal("1000"), currency="INR"),
            ),
            JournalLine(
                account_id=make_entity_id(),
                credit=Money(amount=Decimal("750"), currency="INR"),
            ),
        ]
        with pytest.raises(ValidationError) as excinfo:
            JournalEntry(**_journal_entry_kwargs(make_entity_id, lines))
        msg = str(excinfo.value)
        # The error should be actionable — it calls out the currency and the
        # residual net so a human can see exactly how much is unbalanced.
        assert "INR" in msg
        assert "250" in msg


# --------------------------------------------------------------------------- #
# Reconciliation                                                              #
# --------------------------------------------------------------------------- #


class TestReconciliation:
    def test_reconciliation_basic_construction(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        recon = Reconciliation(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            created_at=now,
            updated_at=now,
            scope=ReconciliationScope.BSP,
            source="bsp_india",
            period=Period(
                start=datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
            items=[],
            summary=ReconciliationSummary(),
        )
        assert recon.scope is ReconciliationScope.BSP
        assert recon.source == "bsp_india"
        assert recon.summary.matched_count == 0


# --------------------------------------------------------------------------- #
# BSPTransaction                                                              #
# --------------------------------------------------------------------------- #


class TestBSPTransaction:
    def test_exchange_kind_constructs_with_signed_amount(self) -> None:
        """``EXCHANGE`` transactions can carry either sign on ``net``.

        A re-fare that credits the passenger back is negative; a re-fare
        that collects more is positive. The canonical model stores the
        sign untouched so downstream aggregation matches the BSP control
        totals.
        """
        tx = BSPTransaction(
            kind=BSPTransactionKind.EXCHANGE,
            document_number="176-7777777777",
            issue_date=date(2026, 4, 14),
            airline="AI",
            gross=Money(amount=Decimal("1200.00"), currency="INR"),
            net=Money(amount=Decimal("1200.00"), currency="INR"),
        )
        assert tx.kind is BSPTransactionKind.EXCHANGE
        assert tx.net.amount == Decimal("1200.00")

        refund_shaped = BSPTransaction(
            kind=BSPTransactionKind.EXCHANGE,
            document_number="176-8888888888",
            issue_date=date(2026, 4, 14),
            airline="AI",
            gross=Money(amount=Decimal("-500.00"), currency="INR"),
            net=Money(amount=Decimal("-500.00"), currency="INR"),
        )
        assert refund_shaped.net.amount == Decimal("-500.00")
