"""Pure mappers: HAF -> canonical, plus reconciliation logic.

No I/O in this module. Everything here is deterministic and side-effect
free so it can be tested in isolation.

**Sign convention.** HAF amounts carry their own sign (positive for
sales, negative for refunds). Canonical :class:`Money` also accepts
signed amounts. We pass signs through unchanged rather than normalising
to absolute values — downstream reporting relies on sign to aggregate
sales vs refunds without a side-table of kinds.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from schemas.canonical import (
    BSPReport,
    BSPTransaction,
    BSPTransactionKind,
    CountryCode,
    EntityId,
    IATACode,
    LocalizedText,
    Money,
    Period,
    Reconciliation,
    ReconciliationItem,
    ReconciliationOutcome,
    ReconciliationScope,
    ReconciliationSummary,
    Ticket,
)

from .haf_records import (
    BFH01FileHeader,
    BFT99FileTrailer,
    BKS24TicketingRecord,
    BKS39RefundRecord,
    BKS45ExchangeRecord,
    BKS46ADMRecord,
    BKS47ACMRecord,
    HAFFile,
    HAFTransactionRecord,
)

logger = logging.getLogger(__name__)


# Amount tolerance for "matched amounts" in reconciliation, in whole
# currency units. Defaults to ±INR 1 — BSP rounds line totals to rupees
# in several places and our internal Decimal math can trail by a paise
# or two on multi-line invoices. This is deliberately loose for v0.
AMOUNT_TOLERANCE = Decimal("1")

# Reconciliation confidence values (basis points, 10_000 == exact).
_CONFIDENCE_EXACT = 10_000
_CONFIDENCE_DISCREPANCY = 8_000
_CONFIDENCE_TENTATIVE = 5_000


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _new_entity_id() -> EntityId:
    """Generate a UUIDv7-shaped id for driver-materialised records.

    Matches the helper in sibling drivers (Amadeus / Tally). Only used
    when the driver itself mints an id — vendor-supplied references flow
    through as ``source_ref`` values, not ``EntityId``.
    """
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _money(amount: Decimal, currency: str) -> Money:
    return Money(amount=amount, currency=currency.upper())


def _iata(value: str) -> IATACode:
    return value.upper()  # type: ignore[return-value]


def _normalised_ticket_key(ticket_number: str, airline_code: str) -> tuple[str, str]:
    """Ticket numbers may or may not carry the 3-digit airline prefix.

    We key reconciliation matches on ``(airline_code, last-10-digits)`` so
    that ``"176-1234567890"`` and ``"1761234567890"`` (and a bare
    ``"1234567890"`` plus airline code) all collide. Non-digit characters
    in the number are stripped.
    """
    digits = "".join(ch for ch in ticket_number if ch.isdigit())
    last10 = digits[-10:] if len(digits) >= 10 else digits
    return (airline_code.upper(), last10)


# --------------------------------------------------------------------------- #
# HAF -> canonical BSPReport                                                  #
# --------------------------------------------------------------------------- #


def _haf_transaction_kind(record: HAFTransactionRecord) -> BSPTransactionKind:
    """Map a parsed HAF record to a canonical :class:`BSPTransactionKind`.

    HAF does not have distinct records for commission and tax adjustments
    at this subset — those only appear as components on a BKS24. They
    are materialised on the :class:`BSPTransaction.commission` / ``taxes``
    fields rather than as their own transaction rows in v0.
    """
    if isinstance(record, BKS24TicketingRecord):
        return BSPTransactionKind.SALE
    if isinstance(record, BKS39RefundRecord):
        return BSPTransactionKind.REFUND
    if isinstance(record, BKS45ExchangeRecord):
        # Exchange is an "in-place" reissue — canonically we treat it as
        # a refund-shaped transaction whose document_number points at the
        # new ticket. Callers that need to treat exchanges separately can
        # inspect the underlying HAF record.
        return BSPTransactionKind.REFUND
    if isinstance(record, BKS46ADMRecord):
        return BSPTransactionKind.ADM
    if isinstance(record, BKS47ACMRecord):
        return BSPTransactionKind.ACM
    raise TypeError(f"Unknown HAF transaction record: {type(record).__name__}")


def _haf_transaction_document_number(record: HAFTransactionRecord) -> str:
    if isinstance(record, BKS24TicketingRecord):
        return record.ticket_number
    if isinstance(record, BKS39RefundRecord):
        return record.document_number
    if isinstance(record, BKS45ExchangeRecord):
        return record.new_ticket_number
    if isinstance(record, (BKS46ADMRecord, BKS47ACMRecord)):
        return record.memo_number
    raise TypeError(f"Unknown HAF transaction record: {type(record).__name__}")


def _haf_transaction_net(record: HAFTransactionRecord) -> Decimal:
    if isinstance(record, BKS24TicketingRecord):
        return record.net_amount
    if isinstance(record, BKS39RefundRecord):
        return record.net_amount
    if isinstance(record, BKS45ExchangeRecord):
        return record.net_amount
    if isinstance(record, (BKS46ADMRecord, BKS47ACMRecord)):
        return record.amount
    raise TypeError(f"Unknown HAF transaction record: {type(record).__name__}")


def _haf_record_to_bsp_transaction(
    record: HAFTransactionRecord, currency: str
) -> BSPTransaction:
    kind = _haf_transaction_kind(record)
    doc = _haf_transaction_document_number(record)
    net = _haf_transaction_net(record)

    # Gross defaults to net for records without an explicit gross
    # component (refunds, exchanges, memos). BKS24 is the one type that
    # carries both.
    if isinstance(record, BKS24TicketingRecord):
        gross = record.gross_fare
        commission = _money(record.commission, currency) if record.commission != 0 else None
    else:
        gross = net
        commission = None

    return BSPTransaction(
        kind=kind,
        document_number=doc,
        issue_date=record.issue_date,
        airline=_iata(record.airline_code),
        gross=_money(gross, currency),
        commission=commission,
        taxes=[],
        net=_money(net, currency),
    )


def _period_from_header(header: BFH01FileHeader) -> Period:
    """Build a canonical :class:`Period` from the HAF header dates.

    BSP India operates a fortnightly settlement cycle; the end date is
    inclusive on the wire. Canonical ``Period`` is a half-open interval,
    so we push ``end`` to the start of the day after ``period_end``.
    """
    from datetime import datetime as _dt

    start = _dt(
        header.period_start.year,
        header.period_start.month,
        header.period_start.day,
        tzinfo=timezone.utc,
    )
    # Half-open: end becomes start-of-day the day AFTER period_end.
    from datetime import timedelta

    end_inclusive = _dt(
        header.period_end.year,
        header.period_end.month,
        header.period_end.day,
        tzinfo=timezone.utc,
    )
    end = end_inclusive + timedelta(days=1)
    return Period(start=start, end=end)


def haf_file_to_bsp_report(haf: HAFFile, tenant_id: EntityId) -> BSPReport:
    """Flatten a :class:`HAFFile` into a canonical :class:`BSPReport`.

    The report aggregates:

    * ``sales_total``       — sum of BKS24 ``gross_fare``.
    * ``refund_total``      — sum of BKS39 / BKS45 ``net_amount``
                              (already signed, typically negative).
    * ``commission_total``  — sum of BKS24 ``commission``.
    * ``net_remittance``    — sum of every transaction's ``net``
                              (== the BSP control total modulo rounding).
    """
    currency = haf.header.bsp_currency.upper()
    country: CountryCode = haf.header.country.upper()  # type: ignore[assignment]

    transactions = [_haf_record_to_bsp_transaction(r, currency) for r in haf.transactions]

    sales_total = Decimal("0")
    refund_total = Decimal("0")
    commission_total = Decimal("0")
    net_total = Decimal("0")
    for record, canonical in zip(haf.transactions, transactions):
        net_total += canonical.net.amount
        if isinstance(record, BKS24TicketingRecord):
            sales_total += record.gross_fare
            commission_total += record.commission
        elif isinstance(record, (BKS39RefundRecord, BKS45ExchangeRecord)):
            refund_total += record.net_amount

    now = datetime.now(timezone.utc)
    return BSPReport(
        id=_new_entity_id(),
        tenant_id=tenant_id,
        country=country,
        period=_period_from_header(haf.header),
        airline=None,
        sales_total=_money(sales_total, currency),
        refund_total=_money(refund_total, currency),
        commission_total=_money(commission_total, currency),
        net_remittance=_money(net_total, currency),
        transactions=transactions,
        source_ref=haf.source_ref,
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# Reconciliation                                                              #
# --------------------------------------------------------------------------- #


def _ticket_index(tickets: Iterable[Ticket]) -> dict[tuple[str, str], Ticket]:
    """Index Voyagent tickets by (airline, last-10-digits-of-number)."""
    index: dict[tuple[str, str], Ticket] = {}
    for t in tickets:
        key = _normalised_ticket_key(t.number, t.issuing_airline)
        if key in index:
            logger.debug(
                "bsp_india.reconcile: duplicate internal ticket key %s (%s); "
                "first wins, later rows will show as UNMATCHED_INTERNAL.",
                key,
                t.number,
            )
            continue
        index[key] = t
    return index


def _amount_within_tolerance(a: Decimal, b: Decimal) -> bool:
    return (a - b).copy_abs() <= AMOUNT_TOLERANCE


def reconcile_bsp_against_tickets(
    report: BSPReport,
    tickets: list[Ticket],
) -> Reconciliation:
    """Deterministic reconciliation of a :class:`BSPReport` against
    Voyagent tickets.

    Rules (v0, no LLM):

    * **MATCHED**        — ticket-number + airline match, amounts within
                           :data:`AMOUNT_TOLERANCE` (confidence 10000).
    * **DISCREPANCY**    — ticket-number + airline match, amounts differ
                           (confidence 8000). ``delta = external - internal``.
    * **UNMATCHED_EXTERNAL** — BSP has a transaction Voyagent has never
                               seen. Common when the agent sold off-platform.
    * **UNMATCHED_INTERNAL** — Voyagent ticket that BSP has not yet
                               billed. Typically a cut-off timing issue
                               (the ticket will appear in the next HAF).
    * **TENTATIVE**      — for v0 this outcome is reserved for fuzzy
                           matches that come close on the airline but
                           fail the normalised ticket-key check. The
                           current rule set does not emit it for
                           numeric-only discrepancies; a v1 fuzzy matcher
                           will.

    Reconciliation is currently restricted to sale-shaped rows (BKS24).
    Refunds (BKS39), exchanges (BKS45), and ADM/ACM memos (BKS46/47) are
    passed through as UNMATCHED_EXTERNAL so the accountant has
    visibility. A v1 pass will link refunds back to their original
    ticket via ``BKS39.original_ticket_number``.
    """
    ticket_index = _ticket_index(tickets)
    matched_internal_keys: set[tuple[str, str]] = set()

    items: list[ReconciliationItem] = []

    matched_count = 0
    unmatched_external_count = 0
    unmatched_internal_count = 0
    discrepancy_count = 0
    tentative_count = 0

    matched_amount_total: Decimal = Decimal("0")
    matched_currency: str | None = None

    for bsp_tx in report.transactions:
        # Only sales are eligible for MATCHED / DISCREPANCY matching in v0.
        if bsp_tx.kind != BSPTransactionKind.SALE:
            items.append(
                ReconciliationItem(
                    outcome=ReconciliationOutcome.UNMATCHED_EXTERNAL,
                    confidence_bps=_CONFIDENCE_EXACT,
                    external_ref=bsp_tx.document_number,
                    external_amount=bsp_tx.net,
                    external_date=bsp_tx.issue_date,
                    internal_refs=[],
                    internal_amount=None,
                    delta=None,
                    evidence=LocalizedText(
                        default=(
                            f"{bsp_tx.kind.value} rows are not auto-matched in v0; "
                            f"accountant review required."
                        )
                    ),
                    suggested_action=LocalizedText(
                        default="Review manually against internal refund/ADM workflow.",
                    ),
                )
            )
            unmatched_external_count += 1
            continue

        key = _normalised_ticket_key(bsp_tx.document_number, bsp_tx.airline)
        internal = ticket_index.get(key)

        if internal is None:
            items.append(
                ReconciliationItem(
                    outcome=ReconciliationOutcome.UNMATCHED_EXTERNAL,
                    confidence_bps=_CONFIDENCE_EXACT,
                    external_ref=bsp_tx.document_number,
                    external_amount=bsp_tx.net,
                    external_date=bsp_tx.issue_date,
                    internal_refs=[],
                    internal_amount=None,
                    delta=None,
                    evidence=LocalizedText(
                        default="BSP billed a ticket with no matching Voyagent record.",
                    ),
                    suggested_action=LocalizedText(
                        default="Confirm whether this was an off-platform sale, then create an internal ticket.",
                    ),
                )
            )
            unmatched_external_count += 1
            continue

        matched_internal_keys.add(key)
        internal_total = internal.total_amount
        external_total = bsp_tx.net

        if internal_total.currency != external_total.currency:
            # Different currency — treat as tentative; operators need to
            # resolve FX before a real reconciliation outcome.
            items.append(
                ReconciliationItem(
                    outcome=ReconciliationOutcome.TENTATIVE,
                    confidence_bps=_CONFIDENCE_TENTATIVE,
                    external_ref=bsp_tx.document_number,
                    external_amount=external_total,
                    external_date=bsp_tx.issue_date,
                    internal_refs=[internal.id],
                    internal_amount=internal_total,
                    delta=None,
                    evidence=LocalizedText(
                        default=(
                            f"Currency mismatch: BSP {external_total.currency} vs "
                            f"internal {internal_total.currency}."
                        )
                    ),
                    suggested_action=LocalizedText(
                        default="Resolve FX posture before accepting this match.",
                    ),
                )
            )
            tentative_count += 1
            continue

        if _amount_within_tolerance(internal_total.amount, external_total.amount):
            matched_count += 1
            if matched_currency is None:
                matched_currency = external_total.currency
            if matched_currency == external_total.currency:
                matched_amount_total += external_total.amount
            items.append(
                ReconciliationItem(
                    outcome=ReconciliationOutcome.MATCHED,
                    confidence_bps=_CONFIDENCE_EXACT,
                    external_ref=bsp_tx.document_number,
                    external_amount=external_total,
                    external_date=bsp_tx.issue_date,
                    internal_refs=[internal.id],
                    internal_amount=internal_total,
                    delta=Money(amount=Decimal("0"), currency=external_total.currency),
                )
            )
        else:
            delta_amount = external_total.amount - internal_total.amount
            discrepancy_count += 1
            items.append(
                ReconciliationItem(
                    outcome=ReconciliationOutcome.DISCREPANCY,
                    confidence_bps=_CONFIDENCE_DISCREPANCY,
                    external_ref=bsp_tx.document_number,
                    external_amount=external_total,
                    external_date=bsp_tx.issue_date,
                    internal_refs=[internal.id],
                    internal_amount=internal_total,
                    delta=Money(amount=delta_amount, currency=external_total.currency),
                    evidence=LocalizedText(
                        default=(
                            f"Amounts differ by {delta_amount} {external_total.currency}."
                        )
                    ),
                    suggested_action=LocalizedText(
                        default="Reconcile the fare/tax breakdown; raise ADM/ACM if appropriate.",
                    ),
                )
            )

    # Internal tickets BSP didn't report this period.
    for key, t in ticket_index.items():
        if key in matched_internal_keys:
            continue
        unmatched_internal_count += 1
        items.append(
            ReconciliationItem(
                outcome=ReconciliationOutcome.UNMATCHED_INTERNAL,
                confidence_bps=_CONFIDENCE_EXACT,
                external_ref=None,
                external_amount=None,
                external_date=None,
                internal_refs=[t.id],
                internal_amount=t.total_amount,
                delta=None,
                evidence=LocalizedText(
                    default="Voyagent ticket not present in this BSP statement.",
                ),
                suggested_action=LocalizedText(
                    default="Check whether BSP will bill it in the next cycle; if not, investigate.",
                ),
            )
        )

    summary = ReconciliationSummary(
        matched_count=matched_count,
        matched_amount=(
            Money(amount=matched_amount_total, currency=matched_currency)
            if matched_currency is not None
            else None
        ),
        unmatched_external_count=unmatched_external_count,
        unmatched_internal_count=unmatched_internal_count,
        discrepancy_count=discrepancy_count,
        tentative_count=tentative_count,
    )

    now = datetime.now(timezone.utc)
    return Reconciliation(
        id=_new_entity_id(),
        tenant_id=report.tenant_id,
        scope=ReconciliationScope.BSP,
        source="bsp_india",
        period=report.period,
        items=items,
        summary=summary,
        created_at=now,
        updated_at=now,
    )


# Silence unused-import warnings for types referenced only by docstrings /
# type hints inside conditional branches.
_ = BFT99FileTrailer


__all__ = [
    "AMOUNT_TOLERANCE",
    "haf_file_to_bsp_report",
    "reconcile_bsp_against_tickets",
]
