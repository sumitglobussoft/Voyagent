"""Pins down the curated IATA airline-code allow-list.

The allow-list doubles as a column-misalignment guard in the HAF
parser: a slice landing on the wrong byte almost always drops a space
or a document-number digit pair into the carrier slot, which these
asserts then reject.
"""

from __future__ import annotations

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers.bsp_india.airlines import (
    IATA_AIRLINE_CODE_RE,
    KNOWN_IATA_AIRLINE_CODES,
    is_known_iata_airline,
)
from drivers.bsp_india.haf_parser import parse_haf

from .conftest import LINE_LENGTH, _bfh01, _bft99, _bks24


# --------------------------------------------------------------------------- #
# IATA_AIRLINE_CODE_RE                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code",
    ["AI", "6E", "SG", "EK", "BA", "UA", "9W", "I5", "AA", "2T"],
)
def test_iata_pattern_accepts_alnum_pairs(code: str) -> None:
    assert IATA_AIRLINE_CODE_RE.match(code)


@pytest.mark.parametrize(
    "code",
    ["a1", "AI1", "A", "", "A-", " A", "ai"],
)
def test_iata_pattern_rejects_malformed_codes(code: str) -> None:
    assert IATA_AIRLINE_CODE_RE.match(code) is None


# --------------------------------------------------------------------------- #
# KNOWN_IATA_AIRLINE_CODES set                                                #
# --------------------------------------------------------------------------- #


def test_allow_list_size_within_reasonable_bounds() -> None:
    """The list is intentionally curated — not exhaustive, not tiny."""
    # Flexible bounds; raise if someone prunes it aggressively or pastes
    # a bulk dump from an unvetted source.
    assert 120 <= len(KNOWN_IATA_AIRLINE_CODES) <= 300


@pytest.mark.parametrize(
    "expected_code",
    [
        # India & subcontinent
        "AI",
        "IX",
        "6E",
        "SG",
        "QP",
        "UK",
        # GCC
        "EK",
        "EY",
        "QR",
        # SE Asia
        "SQ",
        # Europe
        "BA",
        "LH",
        "AF",
        "KL",
        # Americas
        "AA",
        "UA",
        "DL",
    ],
)
def test_allow_list_contains_expected_major_carriers(expected_code: str) -> None:
    assert expected_code in KNOWN_IATA_AIRLINE_CODES


def test_allow_list_contains_only_uppercase_alnum_pairs() -> None:
    for code in KNOWN_IATA_AIRLINE_CODES:
        assert len(code) == 2, code
        assert IATA_AIRLINE_CODE_RE.match(code), code


# --------------------------------------------------------------------------- #
# is_known_iata_airline                                                       #
# --------------------------------------------------------------------------- #


def test_is_known_iata_airline_accepts_known_code() -> None:
    assert is_known_iata_airline("AI") is True


def test_is_known_iata_airline_rejects_unknown_code() -> None:
    # ZZ is reserved / unassigned in IATA and not in our curated list.
    assert is_known_iata_airline("ZZ") is False


def test_is_known_iata_airline_rejects_lowercase() -> None:
    assert is_known_iata_airline("ai") is False


def test_is_known_iata_airline_rejects_wrong_length() -> None:
    assert is_known_iata_airline("A") is False
    assert is_known_iata_airline("AI1") is False


# --------------------------------------------------------------------------- #
# HAF parser wiring: allow-list is applied in practice                         #
# --------------------------------------------------------------------------- #


def test_haf_parser_rejects_bks24_with_unknown_airline_code() -> None:
    # ZZ: well-formed per regex but not in the curated list.
    line = _bks24(
        ticket="1761234567890",
        airline="ZZ",
        issue="20260402",
        gross_cents=100_000,
        commission_cents=0,
        taxes_cents=0,
        net_cents=100_000,
    )
    assert len(line) == LINE_LENGTH
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    trailer = _bft99(3, 100_000)
    content = "\n".join([header, line, trailer]).encode("utf-8") + b"\n"

    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="x")
    assert "not a recognized iata carrier" in str(exc.value).lower()


def test_haf_parser_rejects_bks24_with_malformed_airline_code() -> None:
    """A lowercase/garbage slice fails the regex even before the allow-list."""
    line = _bks24(
        ticket="1761234567890",
        airline="a1",
        issue="20260402",
        gross_cents=100_000,
        commission_cents=0,
        taxes_cents=0,
        net_cents=100_000,
    )
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    trailer = _bft99(3, 100_000)
    content = "\n".join([header, line, trailer]).encode("utf-8") + b"\n"

    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="x")
    assert "not a valid 2-character iata airline code" in str(exc.value).lower()
