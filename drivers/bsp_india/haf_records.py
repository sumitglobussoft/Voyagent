"""Typed record shapes for BSP India HAF files.

HAF (Host-to-Agent File) is defined by IATA RAM Resolution 812g. Every
physical record in a HAF file is a fixed-position line keyed by its first
five characters (the record code, e.g. ``BFH01`` for File Header).

This module defines a small Pydantic data class per record type the v0
driver understands. Record types we do not parse are dropped with a
``logger.debug``; the file header/trailer provide enough context for the
mapper to know it did not observe everything.

These are **driver-layer** shapes. They deliberately do not attempt to
be a faithful mirror of the IATA spec — they capture only the fields the
Voyagent mapper needs to produce canonical :class:`BSPTransaction` and
:class:`BSPReport` instances.

Sign convention: HAF amounts are stored as unsigned decimals in the wire
format with a separate indicator character ``+`` or ``-``. The records
here expose a signed :class:`Decimal` after combining indicator and
magnitude, so the mapper does not have to unpack the indicator again.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class _HAFRecord(BaseModel):
    """Base type for all HAF records. Non-instantiable by convention."""

    model_config = ConfigDict(extra="forbid")

    # Subclasses override with their IATA record code (e.g. ``"BFH01"``).
    record_code: ClassVar[str] = ""


class BFH01FileHeader(_HAFRecord):
    """File Header — one per file.

    Drives the ``country`` / ``currency`` / ``period`` fields on the
    canonical :class:`BSPReport`.
    """

    record_code: ClassVar[str] = "BFH01"

    country: str
    bsp_currency: str
    agent_iata_code: str
    period_start: date
    period_end: date
    file_sequence: str


class BKS24TicketingRecord(_HAFRecord):
    """Agent Ticketing Record — one per ticket sale.

    HAF record code BKS24 in IATA RAM 812g. Amounts are the agent-side
    figures the airline billed through BSP. Taxes are a flat Decimal in
    v0; multi-line tax breakdowns are out of scope until a v1 spec-full
    pass lands.
    """

    record_code: ClassVar[str] = "BKS24"

    ticket_number: str
    airline_code: str
    issue_date: date
    gross_fare: Decimal
    commission: Decimal
    taxes: Decimal
    net_amount: Decimal
    narration: str | None = None


class BKS39RefundRecord(_HAFRecord):
    """Refund Record.

    ``net_amount`` is conventionally negative in HAF — we preserve the
    sign so the mapper can pass it straight through to canonical
    :class:`Money` (which accepts signed amounts).
    """

    record_code: ClassVar[str] = "BKS39"

    document_number: str
    original_ticket_number: str
    airline_code: str
    issue_date: date
    net_amount: Decimal
    narration: str | None = None


class BKS45ExchangeRecord(_HAFRecord):
    """Ticket Exchange / Reissue Record.

    The "additional collect" net amount is often zero for even swaps.
    """

    record_code: ClassVar[str] = "BKS45"

    new_ticket_number: str
    original_ticket_number: str
    airline_code: str
    issue_date: date
    net_amount: Decimal
    narration: str | None = None


class BKS46ADMRecord(_HAFRecord):
    """Agency Debit Memo Record — airline debits the agent."""

    record_code: ClassVar[str] = "BKS46"

    memo_number: str
    airline_code: str
    issue_date: date
    amount: Decimal
    narration: str | None = None


class BKS47ACMRecord(_HAFRecord):
    """Agency Credit Memo Record — airline credits the agent."""

    record_code: ClassVar[str] = "BKS47"

    memo_number: str
    airline_code: str
    issue_date: date
    amount: Decimal
    narration: str | None = None


class BFT99FileTrailer(_HAFRecord):
    """File Trailer — one per file, validates the body.

    ``record_count`` includes header + trailer; ``net_control_total`` is
    the signed sum of every transaction net across the file.
    """

    record_code: ClassVar[str] = "BFT99"

    record_count: int
    net_control_total: Decimal


HAFTransactionRecord = (
    BKS24TicketingRecord
    | BKS39RefundRecord
    | BKS45ExchangeRecord
    | BKS46ADMRecord
    | BKS47ACMRecord
)


class HAFFile(BaseModel):
    """Parsed HAF file — the driver-layer output of :mod:`haf_parser`.

    Not a canonical type; :func:`mapping.haf_file_to_bsp_report` converts
    this into :class:`schemas.canonical.BSPReport`.
    """

    model_config = ConfigDict(extra="forbid")

    header: BFH01FileHeader
    transactions: list[HAFTransactionRecord]
    trailer: BFT99FileTrailer
    source_ref: str


__all__ = [
    "BFH01FileHeader",
    "BFT99FileTrailer",
    "BKS24TicketingRecord",
    "BKS39RefundRecord",
    "BKS45ExchangeRecord",
    "BKS46ADMRecord",
    "BKS47ACMRecord",
    "HAFFile",
    "HAFTransactionRecord",
]
