"""Pure functions that build Tally request envelopes.

Tally's XML is idiosyncratic — tag names are uppercase, attributes are
used sparingly, and certain fields (amounts, dates) have strict formats.
Building via :mod:`lxml` rather than string concatenation guarantees
correct escaping of narration text, ledger names with ampersands, etc.

All functions return a ``bytes`` payload including the XML declaration,
ready to hand to :meth:`TallyClient.post_envelope`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from lxml import etree


# --------------------------------------------------------------------------- #
# Internal line shape                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TallyLedgerEntry:
    """One ledger posting inside a voucher envelope.

    ``amount`` is already signed per Tally's convention: negative for
    the 'deemed-positive' side, positive for the other. See
    :func:`drivers.tally.mapping.journal_entry_to_tally_xml_body` for the
    sign-convention rules.
    """

    ledger_name: str
    amount: Decimal
    is_deemed_positive: bool


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _serialize(root: etree._Element) -> bytes:
    """Serialize an lxml element with Tally's preferred prologue."""
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
        pretty_print=False,
    )


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


def _format_tally_date(d: date) -> str:
    """Tally uses ``YYYYMMDD`` without separators."""
    return d.strftime("%Y%m%d")


def _format_amount(value: Decimal) -> str:
    """Format a decimal amount as Tally expects (two decimals, signed)."""
    return f"{value:.2f}"


def _envelope(request_type: str) -> etree._Element:
    env = etree.Element("ENVELOPE")
    header = _sub(env, "HEADER")
    _sub(header, "TALLYREQUEST", request_type)
    return env


def _export_envelope(report_name: str, collection_id: str | None = None) -> etree._Element:
    env = etree.Element("ENVELOPE")
    header = _sub(env, "HEADER")
    _sub(header, "VERSION", "1")
    _sub(header, "TALLYREQUEST", "Export")
    if collection_id is not None:
        _sub(header, "TYPE", "Collection")
        _sub(header, "ID", collection_id)
    else:
        _sub(header, "TYPE", "Data")
        _sub(header, "ID", report_name)
    return env


# --------------------------------------------------------------------------- #
# Public builders                                                             #
# --------------------------------------------------------------------------- #


def build_ping(company_name: str) -> bytes:
    """Build a lightweight 'Company Info' export request.

    Used as a health-check before heavier calls. Does not require the
    company to be actively loaded, but most errors (company-not-open,
    basic-auth-failed) surface here first.
    """
    env = _export_envelope(report_name="Company Info")
    body = _sub(env, "BODY")
    desc = _sub(body, "DESC")
    static = _sub(desc, "STATICVARIABLES")
    _sub(static, "SVCurrentCompany", company_name)
    return _serialize(env)


def build_list_ledgers(company_name: str) -> bytes:
    """Build a 'List of Ledgers' Collection export request.

    The TDL inside defines a minimal collection over all Ledger masters,
    fetching only the fields the driver needs. Tally ignores unknown
    fields gracefully, so this query is forward-compatible.
    """
    env = _export_envelope(report_name="List of Ledgers", collection_id="List of Ledgers")
    body = _sub(env, "BODY")
    desc = _sub(body, "DESC")
    static = _sub(desc, "STATICVARIABLES")
    _sub(static, "SVCurrentCompany", company_name)
    tdl = _sub(desc, "TDL")
    tdl_msg = _sub(tdl, "TDLMESSAGE")
    collection = etree.SubElement(
        tdl_msg, "COLLECTION", attrib={"NAME": "List of Ledgers", "ISMODIFY": "No"}
    )
    _sub(collection, "TYPE", "Ledger")
    _sub(collection, "FETCH", "NAME, PARENT, OPENINGBALANCE, CURRENCYSYMBOL")
    return _serialize(env)


def build_fetch_voucher(company_name: str, voucher_id: str) -> bytes:
    """Build a request to fetch a single voucher by its Tally master id.

    v0 does not wire this into :class:`TallyDriver` (``read_invoice`` is
    ``not_supported``), but the builder is provided so a future extension
    can call it without re-deriving the envelope shape.
    """
    env = _export_envelope(report_name="Voucher", collection_id="VoucherCollection")
    body = _sub(env, "BODY")
    desc = _sub(body, "DESC")
    static = _sub(desc, "STATICVARIABLES")
    _sub(static, "SVCurrentCompany", company_name)
    _sub(static, "SVVOUCHERID", voucher_id)
    return _serialize(env)


def _voucher_element(
    *,
    vch_type: str,
    entry_date: date,
    narration: str,
    entries: Iterable[TallyLedgerEntry],
    voucher_number: str | None = None,
    reference: str | None = None,
) -> etree._Element:
    """Build a single ``<VOUCHER>`` element used by Journal and Sales imports."""
    voucher = etree.Element("VOUCHER", attrib={"VCHTYPE": vch_type, "ACTION": "Create"})
    _sub(voucher, "DATE", _format_tally_date(entry_date))
    _sub(voucher, "NARRATION", narration)
    _sub(voucher, "VOUCHERTYPENAME", vch_type)
    if voucher_number is not None:
        _sub(voucher, "VOUCHERNUMBER", voucher_number)
    if reference is not None:
        _sub(voucher, "REFERENCE", reference)

    for entry in entries:
        line = _sub(voucher, "ALLLEDGERENTRIES.LIST")
        _sub(line, "LEDGERNAME", entry.ledger_name)
        _sub(line, "ISDEEMEDPOSITIVE", "Yes" if entry.is_deemed_positive else "No")
        _sub(line, "AMOUNT", _format_amount(entry.amount))

    return voucher


def _import_envelope(voucher: etree._Element, company_name: str) -> bytes:
    """Wrap a prepared VOUCHER element in Tally's Import Data envelope."""
    env = _envelope("Import Data")
    body = _sub(env, "BODY")
    importdata = _sub(body, "IMPORTDATA")
    reqdesc = _sub(importdata, "REQUESTDESC")
    _sub(reqdesc, "REPORTNAME", "Vouchers")
    static = _sub(reqdesc, "STATICVARIABLES")
    _sub(static, "SVCurrentCompany", company_name)
    reqdata = _sub(importdata, "REQUESTDATA")
    tally_msg = etree.SubElement(
        reqdata, "TALLYMESSAGE", attrib={"{http://www.w3.org/2000/xmlns/}UDF": "TallyUDF"}
    )
    tally_msg.append(voucher)
    return _serialize(env)


def build_post_journal_voucher(
    company_name: str,
    *,
    entry_date: date,
    narration: str,
    entries: Iterable[TallyLedgerEntry],
    voucher_number: str | None = None,
) -> bytes:
    """Build an Import Data envelope that creates one Journal voucher.

    ``entries`` must already carry Tally-style signed amounts and the
    matching ``ISDEEMEDPOSITIVE`` flag — this builder does not make
    accounting decisions.
    """
    voucher = _voucher_element(
        vch_type="Journal",
        entry_date=entry_date,
        narration=narration,
        entries=entries,
        voucher_number=voucher_number,
    )
    return _import_envelope(voucher, company_name)


def build_post_sales_voucher(
    company_name: str,
    *,
    entry_date: date,
    narration: str,
    entries: Iterable[TallyLedgerEntry],
    voucher_number: str | None = None,
    reference: str | None = None,
) -> bytes:
    """Build an Import Data envelope that creates one Sales voucher.

    Identical shape to the journal builder but tagged ``VCHTYPE=Sales``.
    Tally treats the two as distinct voucher kinds even though the XML
    structure is isomorphic at this level.
    """
    voucher = _voucher_element(
        vch_type="Sales",
        entry_date=entry_date,
        narration=narration,
        entries=entries,
        voucher_number=voucher_number,
        reference=reference,
    )
    return _import_envelope(voucher, company_name)


__all__ = [
    "TallyLedgerEntry",
    "build_fetch_voucher",
    "build_list_ledgers",
    "build_ping",
    "build_post_journal_voucher",
    "build_post_sales_voucher",
]
