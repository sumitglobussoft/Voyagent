"""Parser robustness tests.

Tally emits XML in inconsistent casings, with stray whitespace, comments,
and the occasional non-envelope plain-text body. These tests pin down
the parser's tolerance for those shapes.
"""

from __future__ import annotations

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers.tally.xml_parser import (
    parse_ledger_list,
    parse_ping_response,
    parse_voucher_create_response,
)


# --------------------------------------------------------------------------- #
# parse_ping_response                                                         #
# --------------------------------------------------------------------------- #


def test_parse_ping_response_happy_path(sample_ping_response: bytes) -> None:
    info = parse_ping_response(sample_ping_response)
    assert info.company_name == "Test Travel Agency Pvt Ltd"
    assert info.books_from_date == "20240401"
    assert info.currency == "INR"


def test_parse_ping_response_lowercase_tags_are_accepted() -> None:
    body = (
        b"<?xml version=\"1.0\"?>"
        b"<envelope><body><data>"
        b"<companyname>Acme Travels</companyname>"
        b"</data></body></envelope>"
    )
    info = parse_ping_response(body)
    assert info.company_name == "Acme Travels"


def test_parse_ping_response_rejects_empty_body() -> None:
    with pytest.raises(ValidationFailedError):
        parse_ping_response(b"")


def test_parse_ping_response_rejects_missing_name() -> None:
    body = b"<ENVELOPE><BODY><DATA/></BODY></ENVELOPE>"
    with pytest.raises(ValidationFailedError):
        parse_ping_response(body)


# --------------------------------------------------------------------------- #
# parse_ledger_list                                                           #
# --------------------------------------------------------------------------- #


def test_parse_ledger_list_happy_path(sample_ledger_list_response: bytes) -> None:
    rows = parse_ledger_list(sample_ledger_list_response)
    names = [r.name for r in rows]
    assert "Cash" in names
    assert "CGST Payable" in names
    assert "Proprietor Capital" in names
    parents = {r.name: r.parent for r in rows}
    assert parents["Cash"] == "Cash-in-hand"
    assert parents["CGST Payable"] == "Duties & Taxes"
    assert parents["Proprietor Capital"] == "Capital Account"


def test_parse_ledger_list_tolerates_whitespace_and_comments() -> None:
    body = (
        b"<?xml version=\"1.0\"?>\n"
        b"<ENVELOPE>\n"
        b"  <!-- auto-generated -->\n"
        b"  <BODY><DATA><COLLECTION>\n"
        b"     <LEDGER NAME=\"Petty Cash\">\n"
        b"        <PARENT>Cash-in-hand</PARENT>\n"
        b"     </LEDGER>\n"
        b"  </COLLECTION></DATA></BODY>\n"
        b"</ENVELOPE>\n"
    )
    rows = parse_ledger_list(body)
    assert len(rows) == 1
    assert rows[0].name == "Petty Cash"
    assert rows[0].parent == "Cash-in-hand"


def test_parse_ledger_list_case_insensitive_tag_names() -> None:
    body = (
        b"<envelope><body><data><collection>"
        b"<ledger NAME=\"Mixed Case Ledger\">"
        b"<Parent>Sundry Debtors</Parent>"
        b"</ledger>"
        b"</collection></data></body></envelope>"
    )
    rows = parse_ledger_list(body)
    assert len(rows) == 1
    assert rows[0].parent == "Sundry Debtors"


def test_parse_ledger_list_large(sample_ledger_list_large: bytes) -> None:
    rows = parse_ledger_list(sample_ledger_list_large)
    assert len(rows) == 20
    # Sanity: every row has a name and a parent.
    assert all(r.name and r.parent for r in rows)


def test_parse_ledger_list_skips_rows_without_name() -> None:
    body = (
        b"<ENVELOPE><BODY><DATA><COLLECTION>"
        b"<LEDGER>"
        b"<PARENT>Cash-in-hand</PARENT>"
        b"</LEDGER>"
        b"<LEDGER NAME=\"Good Ledger\">"
        b"<PARENT>Sales Accounts</PARENT>"
        b"</LEDGER>"
        b"</COLLECTION></DATA></BODY></ENVELOPE>"
    )
    rows = parse_ledger_list(body)
    assert len(rows) == 1
    assert rows[0].name == "Good Ledger"


def test_parse_ledger_list_malformed_raises() -> None:
    with pytest.raises(ValidationFailedError):
        parse_ledger_list(b"")


# --------------------------------------------------------------------------- #
# parse_voucher_create_response                                               #
# --------------------------------------------------------------------------- #


def test_parse_voucher_create_response_happy_path(
    sample_voucher_create_response: bytes,
) -> None:
    ack = parse_voucher_create_response(sample_voucher_create_response)
    assert ack.created == 1
    assert ack.altered == 0
    assert ack.last_vch_id == "12345"


def test_parse_voucher_create_response_missing_counts_defaults_to_zero() -> None:
    body = b"<RESPONSE><LASTVCHID>99</LASTVCHID></RESPONSE>"
    ack = parse_voucher_create_response(body)
    assert ack.created == 0
    assert ack.altered == 0
    assert ack.last_vch_id == "99"


def test_parse_voucher_create_response_rejects_empty() -> None:
    with pytest.raises(ValidationFailedError):
        parse_voucher_create_response(b"")
