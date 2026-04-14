"""HAF (Host-to-Agent File) parser.

HAF is the BSP India settlement statement format, defined by IATA
Resolution 812g ("RAM"). The physical layout is fixed-position text: each
logical record is a line whose first five characters are the record code
(e.g. ``BFH01``, ``BKS24``, ``BFT99``) and whose remaining bytes occupy
pre-defined slots within a fixed line length.

**Fixed-position sensitivity.** Parsing here is strict about field
boundaries — we use Python slicing on documented column offsets and never
tokenise with whitespace. Trailing whitespace on a line is tolerated, but
a short line (line length < ``LINE_LENGTH``) is treated as malformed and
raises :class:`ValidationFailedError`.

**UTF-8 mode.** The IATA RAM allows the file to be encoded in UTF-8 for
regions that need non-ASCII narration (Hindi, Kannada, etc.). The parser
decodes the input as UTF-8 with ``errors="strict"`` — non-UTF-8 bytes
raise a parse error rather than silently corrupting narration.

**v0 subset.** The parser recognises:

* ``BFH01`` File Header
* ``BKS24`` Ticketing Record (sale)
* ``BKS39`` Refund Record
* ``BKS45`` Exchange / Reissue Record
* ``BKS46`` ADM Record
* ``BKS47`` ACM Record
* ``BFT99`` File Trailer

Record codes we do not recognise are logged at ``DEBUG`` and skipped —
they stay out of the transaction list but do not fail parsing.

**Column layout (v0).** The layouts below are Voyagent's documented
working layout for the subset above. They are internally consistent and
exercised by the tests in ``tests/drivers/bsp_india/``. They are **not**
a spec-faithful reproduction of IATA RAM 812g — a production driver must
validate against the tenant's own HAF samples before going live.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from drivers._contracts.errors import ValidationFailedError

from .airlines import IATA_AIRLINE_CODE_RE, is_known_iata_airline
from .errors import DRIVER_NAME
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


# --------------------------------------------------------------------------- #
# Physical layout                                                             #
# --------------------------------------------------------------------------- #

# Every HAF record in this layout is exactly LINE_LENGTH bytes long after
# stripping any trailing newline (both "\n" and "\r\n" are tolerated).
LINE_LENGTH = 200

# Amounts in HAF are right-padded numerics with 2 implied decimal places
# and an explicit sign indicator. We keep all sign handling explicit — no
# "positive means sale, negative means refund" inference.
_AMOUNT_SCALE = Decimal("100")


# --------------------------------------------------------------------------- #
# Low-level field helpers                                                     #
# --------------------------------------------------------------------------- #


def _require_line_length(line: str, line_number: int) -> None:
    """Strictly verify line length; trailing whitespace has already been removed."""
    if len(line) != LINE_LENGTH:
        raise ValidationFailedError(
            DRIVER_NAME,
            (
                f"HAF parse error at line {line_number}: expected {LINE_LENGTH}-char "
                f"fixed record, got {len(line)} chars."
            ),
        )


def _slice(line: str, start: int, length: int, *, line_number: int, field: str) -> str:
    """Return the slice at ``[start, start+length)`` with boundary check."""
    end = start + length
    if end > len(line):
        raise ValidationFailedError(
            DRIVER_NAME,
            (
                f"HAF parse error at line {line_number}: field {field!r} extends past "
                f"end of line (start={start}, length={length})."
            ),
        )
    return line[start:end]


def _parse_int(raw: str, *, line_number: int, field: str) -> int:
    s = raw.strip()
    if not s:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: empty integer field {field!r}.",
        )
    try:
        return int(s)
    except ValueError as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: field {field!r} is not an integer ({raw!r}).",
        ) from exc


def _validate_airline_code(raw: str, *, line_number: int, field: str = "airline_code") -> str:
    """Validate an IATA 2-char carrier designator.

    Fails the parse if ``raw`` isn't ``^[A-Z0-9]{2}$`` or isn't in the
    curated allow-list (:mod:`.airlines`). This is the one place
    column-misalignment bugs tend to surface: a bad offset almost
    always drops a space or a digit into this slot.
    """
    code = raw.strip()
    if not IATA_AIRLINE_CODE_RE.match(code):
        raise ValidationFailedError(
            DRIVER_NAME,
            (
                f"HAF parse error at line {line_number}: field {field!r} "
                f"value {raw!r} is not a valid 2-character IATA airline code."
            ),
        )
    if not is_known_iata_airline(code):
        raise ValidationFailedError(
            DRIVER_NAME,
            (
                f"HAF parse error at line {line_number}: HAF airline code "
                f"{code!r} is not a recognized IATA carrier."
            ),
        )
    return code


def _parse_date(raw: str, *, line_number: int, field: str) -> date:
    """Parse a YYYYMMDD date field."""
    s = raw.strip()
    if len(s) != 8 or not s.isdigit():
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: field {field!r} must be YYYYMMDD ({raw!r}).",
        )
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except ValueError as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: invalid date {raw!r} in field {field!r}.",
        ) from exc


def _parse_amount(
    magnitude_raw: str,
    sign_raw: str,
    *,
    line_number: int,
    field: str,
) -> Decimal:
    """Parse an unsigned magnitude + single-character sign ``+``/``-``.

    Magnitudes are encoded with two implied decimal places (cents).
    Returns a signed :class:`Decimal` scaled to the whole-currency unit.
    """
    magnitude = magnitude_raw.strip()
    if not magnitude or not magnitude.isdigit():
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: field {field!r} amount magnitude must be digits ({magnitude_raw!r}).",
        )
    sign_char = sign_raw.strip()
    if sign_char not in ("", "+", "-"):
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: field {field!r} sign must be '+' or '-' ({sign_raw!r}).",
        )
    try:
        value = Decimal(magnitude) / _AMOUNT_SCALE
    except InvalidOperation as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF parse error at line {line_number}: field {field!r} magnitude not a decimal ({magnitude_raw!r}).",
        ) from exc
    if sign_char == "-":
        value = -value
    return value


# --------------------------------------------------------------------------- #
# Per-record parsers                                                          #
# --------------------------------------------------------------------------- #
#
# Layout notes (all offsets are 0-based, slice [start, start+length)):
#
#   BFH01 (File Header)                              len 200
#     0..5   record_code           "BFH01"
#     5..7   country               ISO-3166 alpha-2 ("IN")
#     7..10  currency              ISO-4217 ("INR")
#     10..20 agent_iata_code       right-padded
#     20..28 period_start          YYYYMMDD
#     28..36 period_end            YYYYMMDD
#     36..46 file_sequence         right-padded
#     46..200 filler (spaces)
#
#   BKS24 (Ticketing Record)                         len 200
#     0..5    record_code          "BKS24"
#     5..19   ticket_number        14 chars, right-padded
#     19..21  airline_code         2-letter IATA
#     21..29  issue_date           YYYYMMDD
#     29..41  gross_magnitude      12 digits (cents)
#     41..42  gross_sign           "+"/"-"
#     42..54  commission_magnitude 12 digits
#     54..55  commission_sign      "+"/"-"
#     55..67  taxes_magnitude      12 digits
#     67..68  taxes_sign           "+"/"-"
#     68..80  net_magnitude        12 digits
#     80..81  net_sign             "+"/"-"
#     81..200 narration            119 chars, right-padded
#
#   BKS39 (Refund)                                   len 200
#     0..5    record_code          "BKS39"
#     5..19   document_number      14 chars
#     19..33  original_ticket      14 chars
#     33..35  airline_code         2 chars
#     35..43  issue_date           YYYYMMDD
#     43..55  net_magnitude        12 digits
#     55..56  net_sign             "+"/"-"
#     56..200 narration            144 chars
#
#   BKS45 (Exchange)                                 len 200
#     0..5    record_code          "BKS45"
#     5..19   new_ticket_number    14 chars
#     19..33  original_ticket      14 chars
#     33..35  airline_code         2 chars
#     35..43  issue_date           YYYYMMDD
#     43..55  net_magnitude        12 digits
#     55..56  net_sign             "+"/"-"
#     56..200 narration            144 chars
#
#   BKS46 (ADM) / BKS47 (ACM)                        len 200
#     0..5    record_code
#     5..19   memo_number          14 chars
#     19..21  airline_code         2 chars
#     21..29  issue_date           YYYYMMDD
#     29..41  amount_magnitude     12 digits
#     41..42  amount_sign          "+"/"-"
#     42..200 narration            158 chars
#
#   BFT99 (Trailer)                                  len 200
#     0..5    record_code          "BFT99"
#     5..13   record_count         8 digits
#     13..25  net_magnitude        12 digits
#     25..26  net_sign             "+"/"-"
#     26..200 filler


def _parse_bfh01(line: str, line_number: int) -> BFH01FileHeader:
    country = _slice(line, 5, 2, line_number=line_number, field="country").strip()
    currency = _slice(line, 7, 3, line_number=line_number, field="currency").strip()
    agent = _slice(line, 10, 10, line_number=line_number, field="agent_iata_code").strip()
    start = _parse_date(
        _slice(line, 20, 8, line_number=line_number, field="period_start"),
        line_number=line_number,
        field="period_start",
    )
    end = _parse_date(
        _slice(line, 28, 8, line_number=line_number, field="period_end"),
        line_number=line_number,
        field="period_end",
    )
    seq = _slice(line, 36, 10, line_number=line_number, field="file_sequence").strip()
    return BFH01FileHeader(
        country=country,
        bsp_currency=currency,
        agent_iata_code=agent,
        period_start=start,
        period_end=end,
        file_sequence=seq,
    )


def _parse_bks24(line: str, line_number: int) -> BKS24TicketingRecord:
    ticket = _slice(line, 5, 14, line_number=line_number, field="ticket_number").strip()
    airline = _validate_airline_code(
        _slice(line, 19, 2, line_number=line_number, field="airline_code"),
        line_number=line_number,
    )
    issue = _parse_date(
        _slice(line, 21, 8, line_number=line_number, field="issue_date"),
        line_number=line_number,
        field="issue_date",
    )
    gross = _parse_amount(
        _slice(line, 29, 12, line_number=line_number, field="gross"),
        _slice(line, 41, 1, line_number=line_number, field="gross_sign"),
        line_number=line_number,
        field="gross",
    )
    commission = _parse_amount(
        _slice(line, 42, 12, line_number=line_number, field="commission"),
        _slice(line, 54, 1, line_number=line_number, field="commission_sign"),
        line_number=line_number,
        field="commission",
    )
    taxes = _parse_amount(
        _slice(line, 55, 12, line_number=line_number, field="taxes"),
        _slice(line, 67, 1, line_number=line_number, field="taxes_sign"),
        line_number=line_number,
        field="taxes",
    )
    net = _parse_amount(
        _slice(line, 68, 12, line_number=line_number, field="net"),
        _slice(line, 80, 1, line_number=line_number, field="net_sign"),
        line_number=line_number,
        field="net",
    )
    narration_raw = _slice(line, 81, 119, line_number=line_number, field="narration").rstrip()
    return BKS24TicketingRecord(
        ticket_number=ticket,
        airline_code=airline,
        issue_date=issue,
        gross_fare=gross,
        commission=commission,
        taxes=taxes,
        net_amount=net,
        narration=narration_raw or None,
    )


def _parse_bks39(line: str, line_number: int) -> BKS39RefundRecord:
    doc = _slice(line, 5, 14, line_number=line_number, field="document_number").strip()
    original = _slice(line, 19, 14, line_number=line_number, field="original_ticket_number").strip()
    airline = _validate_airline_code(
        _slice(line, 33, 2, line_number=line_number, field="airline_code"),
        line_number=line_number,
    )
    issue = _parse_date(
        _slice(line, 35, 8, line_number=line_number, field="issue_date"),
        line_number=line_number,
        field="issue_date",
    )
    net = _parse_amount(
        _slice(line, 43, 12, line_number=line_number, field="net"),
        _slice(line, 55, 1, line_number=line_number, field="net_sign"),
        line_number=line_number,
        field="net",
    )
    narration_raw = _slice(line, 56, 144, line_number=line_number, field="narration").rstrip()
    return BKS39RefundRecord(
        document_number=doc,
        original_ticket_number=original,
        airline_code=airline,
        issue_date=issue,
        net_amount=net,
        narration=narration_raw or None,
    )


def _parse_bks45(line: str, line_number: int) -> BKS45ExchangeRecord:
    new_ticket = _slice(line, 5, 14, line_number=line_number, field="new_ticket_number").strip()
    original = _slice(line, 19, 14, line_number=line_number, field="original_ticket_number").strip()
    airline = _validate_airline_code(
        _slice(line, 33, 2, line_number=line_number, field="airline_code"),
        line_number=line_number,
    )
    issue = _parse_date(
        _slice(line, 35, 8, line_number=line_number, field="issue_date"),
        line_number=line_number,
        field="issue_date",
    )
    net = _parse_amount(
        _slice(line, 43, 12, line_number=line_number, field="net"),
        _slice(line, 55, 1, line_number=line_number, field="net_sign"),
        line_number=line_number,
        field="net",
    )
    narration_raw = _slice(line, 56, 144, line_number=line_number, field="narration").rstrip()
    return BKS45ExchangeRecord(
        new_ticket_number=new_ticket,
        original_ticket_number=original,
        airline_code=airline,
        issue_date=issue,
        net_amount=net,
        narration=narration_raw or None,
    )


def _parse_memo(line: str, line_number: int, is_debit: bool) -> BKS46ADMRecord | BKS47ACMRecord:
    memo = _slice(line, 5, 14, line_number=line_number, field="memo_number").strip()
    airline = _validate_airline_code(
        _slice(line, 19, 2, line_number=line_number, field="airline_code"),
        line_number=line_number,
    )
    issue = _parse_date(
        _slice(line, 21, 8, line_number=line_number, field="issue_date"),
        line_number=line_number,
        field="issue_date",
    )
    amount = _parse_amount(
        _slice(line, 29, 12, line_number=line_number, field="amount"),
        _slice(line, 41, 1, line_number=line_number, field="amount_sign"),
        line_number=line_number,
        field="amount",
    )
    narration_raw = _slice(line, 42, 158, line_number=line_number, field="narration").rstrip()
    common = {
        "memo_number": memo,
        "airline_code": airline,
        "issue_date": issue,
        "amount": amount,
        "narration": narration_raw or None,
    }
    return BKS46ADMRecord(**common) if is_debit else BKS47ACMRecord(**common)


def _parse_bft99(line: str, line_number: int) -> BFT99FileTrailer:
    count = _parse_int(
        _slice(line, 5, 8, line_number=line_number, field="record_count"),
        line_number=line_number,
        field="record_count",
    )
    net = _parse_amount(
        _slice(line, 13, 12, line_number=line_number, field="net_control_total"),
        _slice(line, 25, 1, line_number=line_number, field="net_control_total_sign"),
        line_number=line_number,
        field="net_control_total",
    )
    return BFT99FileTrailer(record_count=count, net_control_total=net)


# --------------------------------------------------------------------------- #
# Top-level parser                                                            #
# --------------------------------------------------------------------------- #


def parse_haf(content: bytes, *, source_ref: str) -> HAFFile:
    """Parse a HAF file into a structured :class:`HAFFile`.

    ``content`` must be UTF-8 encoded bytes. Lines may be separated by
    ``"\\n"`` or ``"\\r\\n"``; trailing whitespace on each line is
    tolerated but the stripped line must be exactly
    :data:`LINE_LENGTH` characters long.

    Raises :class:`ValidationFailedError` on:
      * non-UTF-8 bytes,
      * line-length drift,
      * missing / duplicated header or trailer,
      * unparseable individual fields.
    """
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"HAF file is not valid UTF-8: {exc!s}",
        ) from exc

    # Normalise line terminators without altering internal whitespace.
    raw_lines = text.replace("\r\n", "\n").split("\n")
    # Drop a trailing empty line introduced by a final newline.
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()

    header: BFH01FileHeader | None = None
    trailer: BFT99FileTrailer | None = None
    transactions: list[HAFTransactionRecord] = []

    for idx, raw in enumerate(raw_lines, start=1):
        # Preserve leading and internal whitespace; strip only trailing
        # whitespace so "line\t\n" style trailers don't false-positive.
        line = raw.rstrip(" \t")
        if not line:
            continue  # blank separator lines are tolerated

        _require_line_length(line, idx)

        code = line[0:5]
        if code == "BFH01":
            if header is not None:
                raise ValidationFailedError(
                    DRIVER_NAME,
                    f"HAF parse error at line {idx}: duplicate BFH01 header.",
                )
            header = _parse_bfh01(line, idx)
        elif code == "BKS24":
            transactions.append(_parse_bks24(line, idx))
        elif code == "BKS39":
            transactions.append(_parse_bks39(line, idx))
        elif code == "BKS45":
            transactions.append(_parse_bks45(line, idx))
        elif code == "BKS46":
            transactions.append(_parse_memo(line, idx, is_debit=True))
        elif code == "BKS47":
            transactions.append(_parse_memo(line, idx, is_debit=False))
        elif code == "BFT99":
            if trailer is not None:
                raise ValidationFailedError(
                    DRIVER_NAME,
                    f"HAF parse error at line {idx}: duplicate BFT99 trailer.",
                )
            trailer = _parse_bft99(line, idx)
        else:
            logger.debug("bsp_india: skipping unrecognised HAF record %r at line %d", code, idx)

    if header is None:
        raise ValidationFailedError(DRIVER_NAME, "HAF file missing BFH01 header.")
    if trailer is None:
        raise ValidationFailedError(DRIVER_NAME, "HAF file missing BFT99 trailer.")

    return HAFFile(
        header=header,
        transactions=transactions,
        trailer=trailer,
        source_ref=source_ref,
    )


__all__ = ["LINE_LENGTH", "parse_haf"]
