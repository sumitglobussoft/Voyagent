"""HAF -> canonical BSPReport + reconciliation logic."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from drivers.bsp_india.haf_parser import parse_haf
from drivers.bsp_india.mapping import (
    haf_file_to_bsp_report,
    reconcile_bsp_against_tickets,
)
from schemas.canonical import (
    BSPTransactionKind,
    Money,
    ReconciliationOutcome,
    Ticket,
    TicketStatus,
)


pytestmark = pytest.mark.asyncio


def _ticket(
    *,
    id_: str,
    tenant_id: str,
    number: str,
    airline: str,
    total: Decimal,
    pnr_id: str | None = None,
    passenger_id: str | None = None,
) -> Ticket:
    now = datetime.now(timezone.utc)
    return Ticket(
        id=id_,
        tenant_id=tenant_id,
        number=number,
        pnr_id=pnr_id or id_,
        passenger_id=passenger_id or id_,
        issued_at=now,
        issuing_airline=airline,
        issuing_agent_iata="12345678",
        base_amount=Money(amount=total * Decimal("0.9"), currency="INR"),
        tax_amount=Money(amount=total * Decimal("0.1"), currency="INR"),
        total_amount=Money(amount=total, currency="INR"),
        status=TicketStatus.OPEN,
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# haf_file_to_bsp_report                                                      #
# --------------------------------------------------------------------------- #


def test_haf_to_bsp_report_maps_all_records(
    sample_haf_bytes: bytes,
    tenant_id: str,
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    assert report.country == "IN"
    assert report.tenant_id == tenant_id
    assert report.source_ref == "sample-haf"

    kinds = [t.kind for t in report.transactions]
    assert kinds.count(BSPTransactionKind.SALE) == 2
    # BKS39 → REFUND, BKS45 → EXCHANGE (distinct kinds since the
    # canonical enum gained EXCHANGE).
    assert kinds.count(BSPTransactionKind.REFUND) == 1
    assert kinds.count(BSPTransactionKind.EXCHANGE) == 1
    assert kinds.count(BSPTransactionKind.ADM) == 1
    assert kinds.count(BSPTransactionKind.ACM) == 1

    # Aggregates.
    assert report.sales_total.amount == Decimal("45000.00")  # 20000 + 25000
    assert report.commission_total.amount == Decimal("2250.00")
    # refund_total sums BKS39 + BKS45 net signs (both are passed through).
    assert report.refund_total.amount == Decimal("-3800.00")  # -5000 + 1200
    # net_remittance is the sum of *every* transaction net.
    expected_net = Decimal("18500.00") + Decimal("23750.50") + Decimal("-5000.00") + Decimal(
        "1200.00"
    ) + Decimal("500.00") + Decimal("-250.00")
    assert report.net_remittance.amount == expected_net

    for t in report.transactions:
        assert t.gross.currency == "INR"
        assert t.net.currency == "INR"


# --------------------------------------------------------------------------- #
# reconcile_bsp_against_tickets                                               #
# --------------------------------------------------------------------------- #


def test_reconcile_matched_amount_matches_exact(
    sample_haf_bytes: bytes, tenant_id: str, make_id
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    # Create a Voyagent ticket matching the first BKS24 exactly.
    t1 = _ticket(
        id_=make_id(),
        tenant_id=tenant_id,
        number="176-1234567890",  # same digits with a hyphen; matcher strips it
        airline="6E",
        total=Decimal("18500.00"),
    )
    recon = reconcile_bsp_against_tickets(report, [t1])
    matched = [i for i in recon.items if i.outcome == ReconciliationOutcome.MATCHED]
    assert len(matched) == 1
    assert matched[0].confidence_bps == 10_000
    assert matched[0].internal_refs == [t1.id]
    assert matched[0].delta is not None
    assert matched[0].delta.amount == Decimal("0")


def test_reconcile_discrepancy_when_amounts_differ(
    sample_haf_bytes: bytes, tenant_id: str, make_id
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    # A ticket matching the second BKS24 by number + airline, but off by
    # more than the AMOUNT_TOLERANCE (±1 INR).
    t2 = _ticket(
        id_=make_id(),
        tenant_id=tenant_id,
        number="1762222222222",
        airline="AI",
        total=Decimal("23750.00"),  # BSP shows 23750.50
    )
    # AMOUNT_TOLERANCE is 1 INR, difference is 0.50 so this should match.
    # Bump the discrepancy above tolerance:
    t2 = _ticket(
        id_=make_id(),
        tenant_id=tenant_id,
        number="1762222222222",
        airline="AI",
        total=Decimal("23000.00"),  # delta = 750.50
    )
    recon = reconcile_bsp_against_tickets(report, [t2])
    discrepancies = [
        i for i in recon.items if i.outcome == ReconciliationOutcome.DISCREPANCY
    ]
    assert len(discrepancies) == 1
    item = discrepancies[0]
    assert item.internal_refs == [t2.id]
    assert item.delta is not None
    assert item.delta.amount == Decimal("750.50")
    assert item.confidence_bps == 8_000


def test_reconcile_unmatched_external_for_ticket_bsp_knows_but_we_dont(
    sample_haf_bytes: bytes, tenant_id: str
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    recon = reconcile_bsp_against_tickets(report, [])
    unmatched = [
        i for i in recon.items if i.outcome == ReconciliationOutcome.UNMATCHED_EXTERNAL
    ]
    # Two sale rows (neither matched) plus refund/exchange/ADM/ACM rows
    # that always surface as UNMATCHED_EXTERNAL in v0.
    assert len(unmatched) == 6
    assert recon.summary.unmatched_external_count == 6


def test_reconcile_unmatched_internal_for_ticket_bsp_hasnt_billed(
    sample_haf_bytes: bytes, tenant_id: str, make_id
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    # Ticket that BSP has no record of (different airline / number).
    t_orphan = _ticket(
        id_=make_id(),
        tenant_id=tenant_id,
        number="1779999999999",
        airline="UK",
        total=Decimal("5000.00"),
    )
    recon = reconcile_bsp_against_tickets(report, [t_orphan])
    unmatched_internal = [
        i for i in recon.items if i.outcome == ReconciliationOutcome.UNMATCHED_INTERNAL
    ]
    assert len(unmatched_internal) == 1
    assert unmatched_internal[0].internal_refs == [t_orphan.id]
    assert recon.summary.unmatched_internal_count == 1


def test_reconcile_tentative_on_currency_mismatch(
    sample_haf_bytes: bytes, tenant_id: str, make_id
) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample-haf")
    report = haf_file_to_bsp_report(haf, tenant_id=tenant_id)

    # Matching number + airline, but ticket is booked in USD.
    now = datetime.now(timezone.utc)
    t = Ticket(
        id=make_id(),
        tenant_id=tenant_id,
        number="1761234567890",
        pnr_id=make_id(),
        passenger_id=make_id(),
        issued_at=now,
        issuing_airline="6E",
        base_amount=Money(amount=Decimal("200"), currency="USD"),
        tax_amount=Money(amount=Decimal("20"), currency="USD"),
        total_amount=Money(amount=Decimal("220"), currency="USD"),
        status=TicketStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    recon = reconcile_bsp_against_tickets(report, [t])
    tentative = [i for i in recon.items if i.outcome == ReconciliationOutcome.TENTATIVE]
    assert len(tentative) == 1
    assert recon.summary.tentative_count == 1
    assert tentative[0].evidence is not None
    assert "currency mismatch" in tentative[0].evidence.default.lower()
