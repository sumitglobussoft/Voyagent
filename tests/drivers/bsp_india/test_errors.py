"""Error-path tests for the BSP India HAF parser and driver.

``test_haf_parser.py`` already covers line-length drift, missing
header / trailer, and non-UTF-8 bytes. This module adds:

  * a BKS24 record that has been blanked out in the required
    ``issue_date`` columns — the parser must reject with a specific
    error message, not a generic failure,
  * a BKS24 with a non-IATA airline code — the parser currently allows
    any 2-char airline code (no allow-list), so this is tracked as an
    ``xfail`` pointing at the missing validation,
  * ``fetch_statement`` called with the wrong country — must raise
    :class:`ValidationFailedError` before any I/O happens.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from drivers._contracts.errors import ValidationFailedError
from drivers.bsp_india.driver import BSPIndiaDriver
from drivers.bsp_india.haf_parser import parse_haf
from schemas.canonical import Period

from .conftest import LINE_LENGTH, _bfh01, _bft99, _bks24, _pad_right


pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# BKS24: missing required issue_date                                          #
# --------------------------------------------------------------------------- #


def test_haf_bks24_missing_issue_date_raises_validation_failed() -> None:
    """If the BKS24 issue_date slot is blank the parser must reject with a
    message that names the field — not a raw ``ValueError``."""
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    trailer = _bft99(1, 0)

    # Build a BKS24 line then splice blanks into the fixed date columns.
    bks24 = _bks24(
        "1761234567890",
        "6E",
        "20260402",
        gross_cents=100_000,
        commission_cents=0,
        taxes_cents=0,
        net_cents=100_000,
    )
    blanked = bks24[:21] + " " * 8 + bks24[29:]
    assert len(blanked) == LINE_LENGTH

    content = "\n".join([header, blanked, trailer]).encode("utf-8")
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="bad")
    assert "issue_date" in str(exc.value) or "YYYYMMDD" in str(exc.value)


# --------------------------------------------------------------------------- #
# BKS24: unknown airline code                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    reason=(
        "The HAF parser pulls airline_code as a raw 2-char slice with no "
        "validation against an IATA allow-list or the header's declared "
        "agent. A wrong airline code silently becomes part of the parsed "
        "record. Filing this test to document the gap — once the parser "
        "enforces an allow-list it should flip to passing."
    ),
    strict=False,
)
def test_haf_bks24_unknown_airline_code_is_rejected() -> None:
    header = _bfh01("IN", "INR", "12345678", "20260401", "20260415", "0000000001")
    trailer = _bft99(2, 0)
    # "ZZ" is not assigned as a live IATA carrier code.
    bks24 = _bks24(
        "1761234567890",
        "ZZ",
        "20260402",
        gross_cents=100_000,
        commission_cents=0,
        taxes_cents=0,
        net_cents=100_000,
    )
    content = "\n".join([header, bks24, trailer]).encode("utf-8")
    with pytest.raises(ValidationFailedError) as exc:
        parse_haf(content, source_ref="bad")
    assert "airline" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Driver-level: fetch_statement with wrong country                            #
# --------------------------------------------------------------------------- #


async def test_fetch_statement_wrong_country_raises_validation_failed(
    bsp_driver: BSPIndiaDriver,
) -> None:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 15, tzinfo=timezone.utc)
    with pytest.raises(ValidationFailedError) as exc:
        await bsp_driver.fetch_statement("AE", Period(start=start, end=end))
    assert "IN" in str(exc.value) or "not supported" in str(exc.value).lower()
