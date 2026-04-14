"""HAF parser — happy path + malformed input + UTF-8 handling."""

from __future__ import annotations

from decimal import Decimal

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers.bsp_india.haf_parser import LINE_LENGTH, parse_haf
from drivers.bsp_india.haf_records import (
    BKS24TicketingRecord,
    BKS39RefundRecord,
    BKS45ExchangeRecord,
    BKS46ADMRecord,
    BKS47ACMRecord,
)

from .conftest import _bfh01, _bft99, _bks24


pytestmark = pytest.mark.asyncio


def test_parses_header_trailer_and_all_record_kinds(sample_haf_bytes: bytes) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample")
    assert haf.header.country == "IN"
    assert haf.header.bsp_currency == "INR"
    assert haf.header.agent_iata_code == "12345678"
    assert haf.header.period_start.isoformat() == "2026-04-01"
    assert haf.header.period_end.isoformat() == "2026-04-15"

    # 7 transaction records in the fixture.
    kinds = [type(r).__name__ for r in haf.transactions]
    assert kinds == [
        "BKS24TicketingRecord",
        "BKS24TicketingRecord",
        "BKS39RefundRecord",
        "BKS45ExchangeRecord",
        "BKS46ADMRecord",
        "BKS47ACMRecord",
    ]

    # Field-level assertion on first BKS24.
    bks24 = haf.transactions[0]
    assert isinstance(bks24, BKS24TicketingRecord)
    assert bks24.ticket_number == "1761234567890"
    assert bks24.airline_code == "6E"
    assert bks24.gross_fare == Decimal("20000.00")
    assert bks24.commission == Decimal("1000.00")
    assert bks24.taxes == Decimal("500.00")
    assert bks24.net_amount == Decimal("18500.00")

    # Refund carries a negative net.
    refund = haf.transactions[2]
    assert isinstance(refund, BKS39RefundRecord)
    assert refund.net_amount == Decimal("-5000.00")
    assert refund.original_ticket_number == "1761234567890"

    # Exchange carries positive net (additional collect).
    exchange = haf.transactions[3]
    assert isinstance(exchange, BKS45ExchangeRecord)
    assert exchange.net_amount == Decimal("1200.00")

    # Memos.
    adm = haf.transactions[4]
    assert isinstance(adm, BKS46ADMRecord)
    assert adm.amount == Decimal("500.00")
    acm = haf.transactions[5]
    assert isinstance(acm, BKS47ACMRecord)
    assert acm.amount == Decimal("-250.00")

    # Trailer.
    assert haf.trailer.record_count == 9
    assert haf.trailer.net_control_total == Decimal("38700.50")


def test_utf8_narration_survives_round_trip(sample_haf_bytes: bytes) -> None:
    haf = parse_haf(sample_haf_bytes, source_ref="sample")
    # Second BKS24 narration contains Devanagari.
    bks24_2 = haf.transactions[1]
    assert isinstance(bks24_2, BKS24TicketingRecord)
    # The narration field is a fixed 119-character slice; the parser
    # rstrips trailing padding so we expect the meaningful prefix.
    assert bks24_2.narration is not None
    assert "नमस्ते" in bks24_2.narration


def test_malformed_line_length_raises_validation_failed() -> None:
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    trailer = _bft99(2, 0)
    # Corrupt the first body line — chop it to 180 chars.
    bks24 = _bks24(
        "1761234567890",
        "6E",
        "20260402",
        gross_cents=100_000,
        commission_cents=0,
        taxes_cents=0,
        net_cents=100_000,
    )
    short = bks24[:180]
    content = "\n".join([header, short, trailer]).encode("utf-8")
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="bad")
    assert "fixed record" in str(exc.value).lower()
    assert "180" in str(exc.value)


def test_non_utf8_raises_validation_failed() -> None:
    content = b"BFH01" + b"\xff\xfe\xfd" * 70  # not valid UTF-8
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="bad")
    assert "utf-8" in str(exc.value).lower()


def test_missing_header_raises_validation_failed() -> None:
    trailer = _bft99(1, 0)
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(trailer.encode("utf-8") + b"\n", source_ref="x")
    assert "bfh01" in str(exc.value).lower()


def test_missing_trailer_raises_validation_failed() -> None:
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(header.encode("utf-8") + b"\n", source_ref="x")
    assert "bft99" in str(exc.value).lower()


def test_unrecognised_record_is_skipped_not_fatal() -> None:
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    # A made-up 5-letter code padded to LINE_LENGTH.
    unknown = "XXXYZ" + " " * (LINE_LENGTH - 5)
    trailer = _bft99(2, 0)
    content = "\n".join([header, unknown, trailer]).encode("utf-8") + b"\n"
    haf = parse_haf(content, source_ref="x")
    assert haf.transactions == []
