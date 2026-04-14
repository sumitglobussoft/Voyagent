"""Mapping tests — canonical <-> Tally.

Covers every AccountType branch of the parent-group map, and round-trips
a balanced journal entry and a sales-voucher invoice through the builders.
Parsing the emitted bytes back with lxml lets us assert on the wire shape
without pinning exact whitespace / attribute order.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from lxml import etree

from schemas.canonical import (
    AccountType,
    Address,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    JournalEntry,
    JournalLine,
    LocalizedText,
    Money,
    TaxLine,
    TaxRegime,
)

from drivers.tally.mapping import (
    invoice_to_tally_sales_voucher,
    journal_entry_to_tally_xml_body,
    tally_ledger_to_account,
)
from drivers.tally.xml_parser import TallyLedger


def _uuid7() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


# --------------------------------------------------------------------------- #
# Parent-group -> AccountType                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "parent, expected",
    [
        ("Cash-in-hand", AccountType.ASSET),
        ("Bank Accounts", AccountType.ASSET),
        ("Sundry Debtors", AccountType.ASSET),
        ("Fixed Assets", AccountType.ASSET),
        ("Sundry Creditors", AccountType.LIABILITY),
        ("Duties & Taxes", AccountType.LIABILITY),
        ("Loans (Liability)", AccountType.LIABILITY),
        ("Capital Account", AccountType.EQUITY),
        ("Sales Accounts", AccountType.INCOME),
        ("Direct Incomes", AccountType.INCOME),
        ("Indirect Incomes", AccountType.INCOME),
        ("Purchase Accounts", AccountType.EXPENSE),
        ("Direct Expenses", AccountType.EXPENSE),
        ("Indirect Expenses", AccountType.EXPENSE),
    ],
)
def test_ledger_parent_maps_to_correct_account_type(parent: str, expected: AccountType) -> None:
    row = TallyLedger(name="Some Ledger", parent=parent)
    acct = tally_ledger_to_account(row, tenant_id=_uuid7())
    assert acct.type is expected


def test_unknown_parent_defaults_to_expense_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="drivers.tally.mapping")
    row = TallyLedger(name="Weird Ledger", parent="Some Totally Made-Up Group")
    acct = tally_ledger_to_account(row, tenant_id=_uuid7())
    assert acct.type is AccountType.EXPENSE
    assert any("unrecognised parent group" in r.message.lower() for r in caplog.records)


def test_missing_parent_defaults_to_expense_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="drivers.tally.mapping")
    row = TallyLedger(name="Orphan", parent=None)
    acct = tally_ledger_to_account(row, tenant_id=_uuid7())
    assert acct.type is AccountType.EXPENSE
    assert any("no parent" in r.message.lower() for r in caplog.records)


def test_non_iso_currency_symbol_is_dropped() -> None:
    row = TallyLedger(name="Cash", parent="Cash-in-hand", currency="\u20b9")  # rupee sign
    acct = tally_ledger_to_account(row, tenant_id=_uuid7())
    assert acct.currency is None


def test_iso_currency_is_preserved() -> None:
    row = TallyLedger(name="Cash", parent="Cash-in-hand", currency="inr")
    acct = tally_ledger_to_account(row, tenant_id=_uuid7())
    assert acct.currency == "INR"


# --------------------------------------------------------------------------- #
# journal_entry_to_tally_xml_body                                             #
# --------------------------------------------------------------------------- #


def _simple_balanced_entry(tenant: str) -> JournalEntry:
    cash_id = "00000000-0000-7000-8000-000000000005"
    sales_id = "00000000-0000-7000-8000-000000000002"
    now = datetime.now(timezone.utc)
    return JournalEntry(
        id=_uuid7(),
        tenant_id=tenant,
        entry_date=datetime(2026, 4, 14, tzinfo=timezone.utc).date(),
        narration=LocalizedText(default="Cash sale to walk-in customer"),
        lines=[
            JournalLine(
                account_id=cash_id,
                debit=Money(amount=Decimal("1000.00"), currency="INR"),
            ),
            JournalLine(
                account_id=sales_id,
                credit=Money(amount=Decimal("1000.00"), currency="INR"),
            ),
        ],
        source_event="test.cash_sale",
        created_at=now,
        updated_at=now,
    )


def test_journal_entry_to_tally_xml_body_shape(ledger_name_resolver) -> None:
    tenant = _uuid7()
    entry = _simple_balanced_entry(tenant)
    xml = journal_entry_to_tally_xml_body(
        entry, company_name="Test Travel Agency Pvt Ltd", ledger_name_resolver=ledger_name_resolver
    )
    # Must be a valid XML document.
    root = etree.fromstring(xml)
    assert root.tag == "ENVELOPE"
    # Precisely one VOUCHER, VCHTYPE=Journal, ACTION=Create.
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 1
    assert vouchers[0].get("VCHTYPE") == "Journal"
    assert vouchers[0].get("ACTION") == "Create"
    # Date is YYYYMMDD.
    assert vouchers[0].find("DATE").text == "20260414"
    # Narration is preserved verbatim.
    assert vouchers[0].find("NARRATION").text == "Cash sale to walk-in customer"
    # Two ledger lines.
    lines = vouchers[0].findall("ALLLEDGERENTRIES.LIST")
    assert len(lines) == 2
    # Debit line: ISDEEMEDPOSITIVE=Yes, negative amount.
    by_ledger = {ln.find("LEDGERNAME").text: ln for ln in lines}
    cash = by_ledger["Cash-in-hand"]
    assert cash.find("ISDEEMEDPOSITIVE").text == "Yes"
    assert cash.find("AMOUNT").text == "-1000.00"
    # Credit line: ISDEEMEDPOSITIVE=No, positive amount.
    sales = by_ledger["Sales - Domestic"]
    assert sales.find("ISDEEMEDPOSITIVE").text == "No"
    assert sales.find("AMOUNT").text == "1000.00"


def test_journal_entry_company_name_propagates(ledger_name_resolver) -> None:
    tenant = _uuid7()
    xml = journal_entry_to_tally_xml_body(
        _simple_balanced_entry(tenant),
        company_name="My Unique Company Pvt Ltd",
        ledger_name_resolver=ledger_name_resolver,
    )
    root = etree.fromstring(xml)
    companies = root.findall(".//SVCurrentCompany")
    assert companies and companies[0].text == "My Unique Company Pvt Ltd"


# --------------------------------------------------------------------------- #
# invoice_to_tally_sales_voucher                                              #
# --------------------------------------------------------------------------- #


def _tax_line(base: Decimal, rate_bps: int, code: str) -> TaxLine:
    tax_amt = (base * Decimal(rate_bps) / Decimal("10000")).quantize(Decimal("0.01"))
    return TaxLine(
        regime=TaxRegime.GST_INDIA,
        code=code,
        rate_bps=rate_bps,
        taxable_amount=Money(amount=base, currency="INR"),
        tax_amount=Money(amount=tax_amt, currency="INR"),
        jurisdiction="IN",
    )


def test_invoice_to_tally_sales_voucher_builds_expected_lines(ledger_name_resolver) -> None:
    tenant = _uuid7()
    client = "00000000-0000-7000-8000-000000000001"  # resolver knows this
    base = Decimal("10000.00")
    cgst = _tax_line(base, 900, "CGST")
    sgst = _tax_line(base, 900, "SGST")
    grand = base + cgst.tax_amount.amount + sgst.tax_amount.amount

    now = datetime.now(timezone.utc)
    invoice = Invoice(
        id=_uuid7(),
        tenant_id=tenant,
        invoice_number="INV-0001",
        client_id=client,
        issue_date=datetime(2026, 4, 14, tzinfo=timezone.utc).date(),
        currency="INR",
        lines=[
            InvoiceLine(
                description="Consulting",
                quantity=Decimal("1"),
                unit_price=Money(amount=base, currency="INR"),
                subtotal=Money(amount=base, currency="INR"),
                taxes=[cgst, sgst],
                total=Money(amount=base + cgst.tax_amount.amount + sgst.tax_amount.amount, currency="INR"),
            )
        ],
        subtotal=Money(amount=base, currency="INR"),
        tax_total=Money(amount=cgst.tax_amount.amount + sgst.tax_amount.amount, currency="INR"),
        grand_total=Money(amount=grand, currency="INR"),
        status=InvoiceStatus.DRAFT,
        billing_address=Address(country="IN", line1="1 MG Road", city="Bengaluru"),
        notes=LocalizedText(default="Consulting services April 2026"),
        created_at=now,
        updated_at=now,
    )

    xml = invoice_to_tally_sales_voucher(
        invoice,
        company_name="Test Travel Agency Pvt Ltd",
        ledger_name_resolver=ledger_name_resolver,
    )
    root = etree.fromstring(xml)
    voucher = root.find(".//VOUCHER")
    assert voucher is not None
    assert voucher.get("VCHTYPE") == "Sales"
    assert voucher.find("VOUCHERNUMBER").text == "INV-0001"

    lines = voucher.findall("ALLLEDGERENTRIES.LIST")
    # 1 party + 1 sales + 2 tax = 4 lines
    assert len(lines) == 4

    # Party line = debit side.
    party = lines[0]
    assert party.find("LEDGERNAME").text == "Sundry Debtors - Acme Ltd"
    assert party.find("ISDEEMEDPOSITIVE").text == "Yes"
    assert party.find("AMOUNT").text == f"-{grand:.2f}"

    # Sum of credit-side amounts equals grand_total.
    credit_sum = sum(
        Decimal(ln.find("AMOUNT").text)
        for ln in lines[1:]
    )
    assert credit_sum == grand
