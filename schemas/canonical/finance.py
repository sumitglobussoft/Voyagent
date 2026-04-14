"""Finance — v0.

Invoices, payments, journal entries, ledger accounts, BSP, and
reconciliations. These are the accounting-grade primitives that accountants
will judge the product on — so they must be precise.

Double-entry invariants live in this module. Country-specific tax filings
(GST-India, TDS, VAT, HMRC filings) sit behind country-scoped drivers; the
canonical types here are globalization-safe.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from .primitives import (
    Address,
    CountryCode,
    CurrencyCode,
    EntityId,
    IATACode,
    LocalizedText,
    Money,
    Period,
    TaxLine,
    Timestamps,
    _strict,
)

# --------------------------------------------------------------------------- #
# Invoice                                                                     #
# --------------------------------------------------------------------------- #


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class InvoiceLine(BaseModel):
    """One chargeable item on an invoice."""

    model_config = _strict()

    description: str
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    unit_price: Money
    subtotal: Money
    taxes: list[TaxLine] = Field(default_factory=list)
    total: Money

    references: dict[str, EntityId] = Field(
        default_factory=dict,
        description="Optional refs to upstream records: {'booking_id': ..., 'pnr_id': ..., 'ticket_id': ...}.",
    )

    @model_validator(mode="after")
    def _currency_consistency(self) -> InvoiceLine:
        currencies = {self.unit_price.currency, self.subtotal.currency, self.total.currency}
        currencies.update(t.tax_amount.currency for t in self.taxes)
        if len(currencies) > 1:
            raise ValueError(f"Invoice line amounts must share a currency (found {currencies}).")
        return self


class Invoice(Timestamps):
    """A customer-facing bill.

    Invoice numbering series are tenant-configurable — multiple series per
    tenant are common (domestic / international / refunds). The runtime owns
    series allocation; the canonical record just stores the assigned number.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    invoice_number: str
    series: str | None = Field(default=None, description="Series label for tenants that run multiple numbering series.")

    client_id: EntityId
    booking_ids: list[EntityId] = Field(default_factory=list)

    issue_date: date
    due_date: date | None = None
    currency: CurrencyCode

    lines: list[InvoiceLine] = Field(min_length=1)
    subtotal: Money
    tax_total: Money
    grand_total: Money

    status: InvoiceStatus = InvoiceStatus.DRAFT
    billing_address: Address
    notes: LocalizedText | None = None

    @model_validator(mode="after")
    def _currency_consistency(self) -> Invoice:
        for money in (self.subtotal, self.tax_total, self.grand_total):
            if money.currency != self.currency:
                raise ValueError(
                    f"Invoice totals must match invoice currency ({self.currency}); got {money.currency}."
                )
        for line in self.lines:
            if line.total.currency != self.currency:
                raise ValueError(
                    f"Invoice line currency ({line.total.currency}) must match invoice currency ({self.currency})."
                )
        return self


# --------------------------------------------------------------------------- #
# Payment & Receipt                                                           #
# --------------------------------------------------------------------------- #


class PaymentDirection(StrEnum):
    INBOUND = "inbound"     # from a client
    OUTBOUND = "outbound"   # to a supplier


class PaymentMethod(StrEnum):
    """Extensible enum. Country-specific rails (UPI, SEPA, ACH, Wise) are
    implemented as PaymentDrivers; this enum only names the canonical family."""

    UPI = "upi"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CHEQUE = "cheque"
    PAYMENT_LINK = "payment_link"
    WALLET = "wallet"
    OTHER = "other"


class PaymentStatus(StrEnum):
    INITIATED = "initiated"
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    REVERSED = "reversed"


class Payment(Timestamps):
    """A money movement in or out of the agency's accounts."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    direction: PaymentDirection
    amount: Money
    method: PaymentMethod
    counterparty_id: EntityId = Field(description="Client id for INBOUND, supplier/account id for OUTBOUND.")

    initiated_at: datetime
    settled_at: datetime | None = None
    status: PaymentStatus = PaymentStatus.INITIATED

    source: str = Field(description="Driver that handled the rail: 'razorpay', 'stripe', 'hdfc_bank', 'tally_manual', ...")
    source_ref: str | None = None

    invoice_id: EntityId | None = None
    bill_id: EntityId | None = None


class Receipt(Timestamps):
    """A receipt issued against one or more payments. Legally distinct from
    the Payment itself in some jurisdictions; always has its own numbering."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    receipt_number: str
    payment_ids: list[EntityId] = Field(min_length=1)
    client_id: EntityId
    issued_at: datetime
    total: Money


# --------------------------------------------------------------------------- #
# Ledger                                                                      #
# --------------------------------------------------------------------------- #


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class LedgerAccount(Timestamps):
    """A chart-of-accounts node.

    `code` is tenant-defined — preserved as-is so exports to Tally / Zoho /
    QuickBooks retain the tenant's existing chart. Currency is optional to
    support multi-currency accounts where the backing system supports them.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    code: str
    name: LocalizedText
    type: AccountType
    parent_id: EntityId | None = None
    currency: CurrencyCode | None = None
    is_active: bool = True


class JournalLine(BaseModel):
    """One side of a double-entry line. Exactly one of debit/credit is set."""

    model_config = _strict()

    account_id: EntityId
    debit: Money | None = None
    credit: Money | None = None
    narration: str | None = None
    reference: EntityId | None = None

    @model_validator(mode="after")
    def _exactly_one_side(self) -> JournalLine:
        if (self.debit is None) == (self.credit is None):
            raise ValueError("JournalLine must set exactly one of debit / credit.")
        return self


class JournalEntry(Timestamps):
    """A double-entry journal voucher.

    Invariant: for each currency present on the lines, total debits equal
    total credits. Multi-currency entries are allowed (common for FX gain/loss
    entries) but must balance per currency.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    entry_date: date
    narration: LocalizedText
    lines: list[JournalLine] = Field(min_length=2)

    source_event: str = Field(
        description="What caused this entry: 'invoice.issued', 'payment.settled', 'reconciliation.adjust', ...",
    )
    source_ref: EntityId | None = None

    @model_validator(mode="after")
    def _balanced_per_currency(self) -> JournalEntry:
        by_currency: dict[str, Decimal] = {}
        for line in self.lines:
            money = line.debit if line.debit is not None else line.credit
            assert money is not None  # validator on JournalLine guarantees
            sign = Decimal("1") if line.debit is not None else Decimal("-1")
            by_currency[money.currency] = by_currency.get(money.currency, Decimal("0")) + sign * money.amount
        for currency, net in by_currency.items():
            if net != 0:
                raise ValueError(f"Journal entry not balanced in {currency}: net = {net}.")
        return self


# --------------------------------------------------------------------------- #
# BSP                                                                         #
# --------------------------------------------------------------------------- #


class BSPTransactionKind(StrEnum):
    SALE = "sale"
    REFUND = "refund"
    ADM = "adm"          # Agency Debit Memo
    ACM = "acm"          # Agency Credit Memo
    COMMISSION = "commission"
    TAX_ADJUSTMENT = "tax_adjustment"


class BSPTransaction(BaseModel):
    model_config = _strict()

    kind: BSPTransactionKind
    document_number: str = Field(description="Ticket number, ADM/ACM reference, or refund document number.")
    issue_date: date
    airline: IATACode
    gross: Money
    commission: Money | None = None
    taxes: list[TaxLine] = Field(default_factory=list)
    net: Money
    internal_ticket_id: EntityId | None = Field(default=None, description="Voyagent Ticket id if matched.")


class BSPReport(Timestamps):
    """A parsed BSP settlement statement.

    BSP operates globally under IATA, with different settlement cycles per
    country. `country` drives which BSP driver parsed the file.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    country: CountryCode
    period: Period
    airline: IATACode | None = Field(default=None, description="Set when the statement is airline-scoped; None for the full multi-airline settlement.")

    sales_total: Money
    refund_total: Money
    commission_total: Money
    net_remittance: Money

    transactions: list[BSPTransaction] = Field(default_factory=list)
    source_ref: str = Field(description="BSP file identifier or settlement reference.")


# --------------------------------------------------------------------------- #
# Reconciliation                                                              #
# --------------------------------------------------------------------------- #


class ReconciliationScope(StrEnum):
    BSP = "bsp"
    BANK = "bank"
    CARD = "card"
    SUPPLIER = "supplier"
    PAYMENT_GATEWAY = "payment_gateway"
    CLIENT_STATEMENT = "client_statement"


class ReconciliationOutcome(StrEnum):
    MATCHED = "matched"
    UNMATCHED_EXTERNAL = "unmatched_external"   # external record has no internal counterpart
    UNMATCHED_INTERNAL = "unmatched_internal"   # internal record has no external counterpart
    DISCREPANCY = "discrepancy"                 # matched but amounts or details disagree
    TENTATIVE = "tentative"                     # fuzzy match below confidence threshold


class ReconciliationItem(BaseModel):
    """One row of reconciliation output. Must carry enough evidence for an
    accountant to act on it without re-doing the work."""

    model_config = _strict()

    outcome: ReconciliationOutcome
    confidence_bps: int = Field(ge=0, le=10_000, description="0–10000 where 10000 == exact match.")

    external_ref: str | None = None
    external_amount: Money | None = None
    external_date: date | None = None

    internal_refs: list[EntityId] = Field(default_factory=list)
    internal_amount: Money | None = None

    delta: Money | None = Field(default=None, description="external - internal when both present.")
    evidence: LocalizedText | None = None
    suggested_action: LocalizedText | None = None


class ReconciliationSummary(BaseModel):
    model_config = _strict()

    matched_count: int = 0
    matched_amount: Money | None = None
    unmatched_external_count: int = 0
    unmatched_internal_count: int = 0
    discrepancy_count: int = 0
    tentative_count: int = 0


class Reconciliation(Timestamps):
    """A reconciliation run against one external source over a period."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    scope: ReconciliationScope
    source: str = Field(description="Driver identifier: 'bsp_india', 'hdfc_bank', 'razorpay', 'hotelbeds', ...")
    period: Period

    items: list[ReconciliationItem] = Field(default_factory=list)
    summary: ReconciliationSummary


__all__ = [
    "AccountType",
    "BSPReport",
    "BSPTransaction",
    "BSPTransactionKind",
    "Invoice",
    "InvoiceLine",
    "InvoiceStatus",
    "JournalEntry",
    "JournalLine",
    "LedgerAccount",
    "Payment",
    "PaymentDirection",
    "PaymentMethod",
    "PaymentStatus",
    "Receipt",
    "Reconciliation",
    "ReconciliationItem",
    "ReconciliationOutcome",
    "ReconciliationScope",
    "ReconciliationSummary",
]
