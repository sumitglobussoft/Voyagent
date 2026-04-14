"""Pure-function tests for :mod:`drivers.tally.xml_builder`.

These pin down the shape of the XML the driver sends to Tally — tag
names, attribute presence, date/amount formatting — without going
through :class:`TallyDriver` (which adds HTTP + resolver concerns).

We parse the emitted bytes with lxml and assert on the tree rather than
byte-comparing, so whitespace / attribute-order changes never cause a
false negative.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from drivers.tally.xml_builder import (
    TallyLedgerEntry,
    build_fetch_voucher,
    build_list_ledgers,
    build_ping,
    build_post_journal_voucher,
    build_post_sales_voucher,
)


COMPANY = "Test Travel Agency Pvt Ltd"


def _parse(blob: bytes) -> etree._Element:
    # lxml rejects trailing whitespace from XML_DECLARATION by default;
    # strip the BOM if present, but the builder does not emit one.
    return etree.fromstring(blob)


# --------------------------------------------------------------------------- #
# build_ping                                                                  #
# --------------------------------------------------------------------------- #


def test_build_ping_emits_export_envelope_with_company_name() -> None:
    out = build_ping(COMPANY)
    root = _parse(out)
    assert root.tag == "ENVELOPE"
    assert root.findtext("HEADER/TALLYREQUEST") == "Export"
    assert root.findtext("HEADER/TYPE") == "Data"
    assert root.findtext("HEADER/ID") == "Company Info"
    assert root.findtext("BODY/DESC/STATICVARIABLES/SVCurrentCompany") == COMPANY


def test_build_ping_has_xml_declaration_and_utf8() -> None:
    out = build_ping(COMPANY)
    head = out[:64].decode("ascii", errors="replace")
    assert head.startswith("<?xml")
    assert "UTF-8" in head


# --------------------------------------------------------------------------- #
# build_list_ledgers                                                          #
# --------------------------------------------------------------------------- #


def test_build_list_ledgers_declares_ledger_collection() -> None:
    out = build_list_ledgers(COMPANY)
    root = _parse(out)
    assert root.findtext("HEADER/TYPE") == "Collection"
    assert root.findtext("HEADER/ID") == "List of Ledgers"

    collection = root.find("BODY/DESC/TDL/TDLMESSAGE/COLLECTION")
    assert collection is not None
    assert collection.get("NAME") == "List of Ledgers"
    assert collection.get("ISMODIFY") == "No"
    assert collection.findtext("TYPE") == "Ledger"
    # FETCH fields we rely on in the parser.
    fetch = collection.findtext("FETCH") or ""
    for field in ("NAME", "PARENT", "OPENINGBALANCE", "CURRENCYSYMBOL"):
        assert field in fetch


def test_build_list_ledgers_scopes_to_given_company() -> None:
    out = build_list_ledgers("Other Co Ltd")
    root = _parse(out)
    assert (
        root.findtext("BODY/DESC/STATICVARIABLES/SVCurrentCompany") == "Other Co Ltd"
    )


# --------------------------------------------------------------------------- #
# build_fetch_voucher                                                         #
# --------------------------------------------------------------------------- #


def test_build_fetch_voucher_carries_voucher_id() -> None:
    out = build_fetch_voucher(COMPANY, voucher_id="42")
    root = _parse(out)
    assert root.findtext("HEADER/ID") == "VoucherCollection"
    static = root.find("BODY/DESC/STATICVARIABLES")
    assert static is not None
    assert static.findtext("SVCurrentCompany") == COMPANY
    assert static.findtext("SVVOUCHERID") == "42"


# --------------------------------------------------------------------------- #
# build_post_journal_voucher                                                  #
# --------------------------------------------------------------------------- #


def _balanced_entries() -> list[TallyLedgerEntry]:
    return [
        TallyLedgerEntry(
            ledger_name="Cash-in-hand",
            amount=Decimal("-500.00"),
            is_deemed_positive=True,
        ),
        TallyLedgerEntry(
            ledger_name="Sales - Domestic",
            amount=Decimal("500.00"),
            is_deemed_positive=False,
        ),
    ]


def test_build_post_journal_voucher_has_import_data_envelope() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="Daily cash sale",
        entries=_balanced_entries(),
    )
    root = _parse(out)
    assert root.findtext("HEADER/TALLYREQUEST") == "Import Data"
    reqdesc = root.find("BODY/IMPORTDATA/REQUESTDESC")
    assert reqdesc is not None
    assert reqdesc.findtext("REPORTNAME") == "Vouchers"
    assert reqdesc.findtext("STATICVARIABLES/SVCurrentCompany") == COMPANY


def test_build_post_journal_voucher_formats_date_as_yyyymmdd() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="x",
        entries=_balanced_entries(),
    )
    root = _parse(out)
    voucher = root.find(".//VOUCHER")
    assert voucher is not None
    assert voucher.findtext("DATE") == "20260414"


def test_build_post_journal_voucher_is_tagged_journal() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="x",
        entries=_balanced_entries(),
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    assert voucher.get("VCHTYPE") == "Journal"
    assert voucher.get("ACTION") == "Create"
    assert voucher.findtext("VOUCHERTYPENAME") == "Journal"


def test_build_post_journal_voucher_emits_one_line_per_entry() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="x",
        entries=_balanced_entries(),
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    lines = voucher.findall("ALLLEDGERENTRIES.LIST")
    assert len(lines) == 2
    assert lines[0].findtext("LEDGERNAME") == "Cash-in-hand"
    assert lines[0].findtext("ISDEEMEDPOSITIVE") == "Yes"
    assert lines[0].findtext("AMOUNT") == "-500.00"
    assert lines[1].findtext("LEDGERNAME") == "Sales - Domestic"
    assert lines[1].findtext("ISDEEMEDPOSITIVE") == "No"
    assert lines[1].findtext("AMOUNT") == "500.00"


def test_build_post_journal_voucher_preserves_narration_with_special_chars() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="Journal entry for Maersk & Co <internal>",
        entries=_balanced_entries(),
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    # lxml decodes entities on read; the escaping round-trips correctly.
    assert voucher.findtext("NARRATION") == "Journal entry for Maersk & Co <internal>"


def test_build_post_journal_voucher_preserves_ledger_name_with_ampersand() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="x",
        entries=[
            TallyLedgerEntry(
                ledger_name="Duties & Taxes - CGST",
                amount=Decimal("-90.00"),
                is_deemed_positive=True,
            ),
            TallyLedgerEntry(
                ledger_name="Sales",
                amount=Decimal("90.00"),
                is_deemed_positive=False,
            ),
        ],
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    first = voucher.findall("ALLLEDGERENTRIES.LIST")[0]
    assert first.findtext("LEDGERNAME") == "Duties & Taxes - CGST"


def test_build_post_journal_voucher_amount_format_has_two_decimals() -> None:
    out = build_post_journal_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="x",
        entries=[
            TallyLedgerEntry(
                ledger_name="Cash-in-hand",
                amount=Decimal("-500"),
                is_deemed_positive=True,
            ),
            TallyLedgerEntry(
                ledger_name="Sales",
                amount=Decimal("500"),
                is_deemed_positive=False,
            ),
        ],
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    amounts = [ln.findtext("AMOUNT") for ln in voucher.findall("ALLLEDGERENTRIES.LIST")]
    for a in amounts:
        assert a.count(".") == 1
        # Exactly two digits after the decimal.
        assert len(a.split(".")[1]) == 2


# --------------------------------------------------------------------------- #
# build_post_sales_voucher                                                    #
# --------------------------------------------------------------------------- #


def test_build_post_sales_voucher_is_tagged_sales() -> None:
    out = build_post_sales_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="Invoice INV-42",
        entries=_balanced_entries(),
        voucher_number="INV-42",
        reference="INV-42",
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    assert voucher.get("VCHTYPE") == "Sales"
    assert voucher.findtext("VOUCHERTYPENAME") == "Sales"
    assert voucher.findtext("VOUCHERNUMBER") == "INV-42"
    assert voucher.findtext("REFERENCE") == "INV-42"


def test_build_post_sales_voucher_omits_voucher_number_when_not_supplied() -> None:
    out = build_post_sales_voucher(
        COMPANY,
        entry_date=date(2026, 4, 14),
        narration="Invoice",
        entries=_balanced_entries(),
    )
    voucher = _parse(out).find(".//VOUCHER")
    assert voucher is not None
    assert voucher.find("VOUCHERNUMBER") is None
    assert voucher.find("REFERENCE") is None
