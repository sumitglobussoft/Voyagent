"""Shared fixtures for the BSP India driver test suite.

The sample HAF file below is synthesised from the record-layout notes in
``drivers/bsp_india/haf_parser.py``. It is **not** a real BSP production
file — it is a self-consistent set of fixed-position records whose field
values are chosen to exercise the mapper and the reconciliation logic.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
import pytest_asyncio

from drivers.bsp_india.config import BSPIndiaConfig
from drivers.bsp_india.driver import BSPIndiaDriver


# --------------------------------------------------------------------------- #
# Id helper                                                                   #
# --------------------------------------------------------------------------- #


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


@pytest.fixture
def tenant_id() -> str:
    return _uuid7_like()


@pytest.fixture
def make_id() -> Callable[[], str]:
    return _uuid7_like


# --------------------------------------------------------------------------- #
# HAF record builders                                                         #
# --------------------------------------------------------------------------- #


LINE_LENGTH = 200


def _pad_right(value: str, width: int) -> str:
    if len(value) > width:
        raise ValueError(f"value {value!r} exceeds width {width}")
    return value + " " * (width - len(value))


def _digits(value: int | str, width: int) -> str:
    s = str(value)
    if len(s) > width:
        raise ValueError(f"digit field {s!r} exceeds width {width}")
    return s.rjust(width, "0")


def _amount(signed_cents: int) -> tuple[str, str]:
    """Return (magnitude12, sign1) for ``signed_cents`` (two implied decimals)."""
    sign = "+" if signed_cents >= 0 else "-"
    magnitude = _digits(abs(signed_cents), 12)
    return magnitude, sign


def _bfh01(country: str, currency: str, agent: str, start: str, end: str, seq: str) -> str:
    line = (
        "BFH01"
        + _pad_right(country, 2)
        + _pad_right(currency, 3)
        + _pad_right(agent, 10)
        + _pad_right(start, 8)
        + _pad_right(end, 8)
        + _pad_right(seq, 10)
    )
    return _pad_right(line, LINE_LENGTH)


def _bks24(
    ticket: str,
    airline: str,
    issue: str,
    gross_cents: int,
    commission_cents: int,
    taxes_cents: int,
    net_cents: int,
    narration: str = "",
) -> str:
    gm, gs = _amount(gross_cents)
    cm, cs = _amount(commission_cents)
    tm, ts = _amount(taxes_cents)
    nm, ns = _amount(net_cents)
    line = (
        "BKS24"
        + _pad_right(ticket, 14)
        + _pad_right(airline, 2)
        + issue
        + gm + gs
        + cm + cs
        + tm + ts
        + nm + ns
        + _pad_right(narration, 119)
    )
    return _pad_right(line, LINE_LENGTH)


def _bks39(
    doc: str,
    original: str,
    airline: str,
    issue: str,
    net_cents: int,
    narration: str = "",
) -> str:
    nm, ns = _amount(net_cents)
    line = (
        "BKS39"
        + _pad_right(doc, 14)
        + _pad_right(original, 14)
        + _pad_right(airline, 2)
        + issue
        + nm + ns
        + _pad_right(narration, 144)
    )
    return _pad_right(line, LINE_LENGTH)


def _bks45(
    new_ticket: str,
    original: str,
    airline: str,
    issue: str,
    net_cents: int,
    narration: str = "",
) -> str:
    nm, ns = _amount(net_cents)
    line = (
        "BKS45"
        + _pad_right(new_ticket, 14)
        + _pad_right(original, 14)
        + _pad_right(airline, 2)
        + issue
        + nm + ns
        + _pad_right(narration, 144)
    )
    return _pad_right(line, LINE_LENGTH)


def _memo(code: str, memo_number: str, airline: str, issue: str, amount_cents: int, narration: str = "") -> str:
    am, asgn = _amount(amount_cents)
    line = (
        code
        + _pad_right(memo_number, 14)
        + _pad_right(airline, 2)
        + issue
        + am + asgn
        + _pad_right(narration, 158)
    )
    return _pad_right(line, LINE_LENGTH)


def _bft99(record_count: int, net_control_cents: int) -> str:
    nm, ns = _amount(net_control_cents)
    line = (
        "BFT99"
        + _digits(record_count, 8)
        + nm + ns
    )
    return _pad_right(line, LINE_LENGTH)


# --------------------------------------------------------------------------- #
# Sample file                                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def sample_haf_bytes() -> bytes:
    """A self-consistent HAF file with one of each supported record type.

    Amounts (in paise / cents):
      * BKS24 sale — ticket 1761234567890, airline 6E — net +18500.00
      * BKS24 sale — ticket 1762222222222, airline AI — net +23750.50
      * BKS39 refund — document 1763333333333 — net -5000.00
      * BKS45 exchange — new ticket 1764444444444 — net +1200.00
      * BKS46 ADM — memo number ADM00000000001 — amount +500.00
      * BKS47 ACM — memo number ACM00000000001 — amount -250.00 (credit)
      * One UTF-8 narration exercising non-ASCII bytes.

    Net control total = 18500 + 23750.50 - 5000 + 1200 + 500 - 250 = 38700.50
    """
    lines: list[str] = []
    lines.append(
        _bfh01(
            country="IN",
            currency="INR",
            agent="12345678",
            start="20260401",
            end="20260415",
            seq="0000000001",
        )
    )
    lines.append(
        _bks24(
            ticket="1761234567890",
            airline="6E",
            issue="20260402",
            gross_cents=2_000_000,  # 20000.00
            commission_cents=100_000,  # 1000.00
            taxes_cents=50_000,  # 500.00
            net_cents=1_850_000,  # 18500.00
            narration="Mumbai-Delhi economy",
        )
    )
    lines.append(
        _bks24(
            ticket="1762222222222",
            airline="AI",
            issue="20260403",
            gross_cents=2_500_000,
            commission_cents=125_000,
            taxes_cents=75_000,
            net_cents=2_375_050,  # 23750.50
            narration="Delhi-LHR with non-ASCII: नमस्ते",
        )
    )
    lines.append(
        _bks39(
            doc="1763333333333",
            original="1761234567890",
            airline="6E",
            issue="20260405",
            net_cents=-500_000,  # -5000.00
            narration="Partial refund",
        )
    )
    lines.append(
        _bks45(
            new_ticket="1764444444444",
            original="1762222222222",
            airline="AI",
            issue="20260406",
            net_cents=120_000,  # +1200.00
            narration="Reissue / exchange",
        )
    )
    lines.append(
        _memo(
            "BKS46",
            memo_number="ADM00000000001",
            airline="6E",
            issue="20260407",
            amount_cents=50_000,
            narration="Tariff violation",
        )
    )
    lines.append(
        _memo(
            "BKS47",
            memo_number="ACM00000000001",
            airline="AI",
            issue="20260408",
            amount_cents=-25_000,
            narration="Goodwill credit",
        )
    )
    # 7 body records + header + trailer = 9 total records.
    lines.append(_bft99(record_count=9, net_control_cents=3_870_050))

    content = "\n".join(lines) + "\n"
    return content.encode("utf-8")


# --------------------------------------------------------------------------- #
# Driver fixture                                                              #
# --------------------------------------------------------------------------- #


@pytest.fixture
def bsp_config(tmp_path: Path) -> BSPIndiaConfig:
    drop = tmp_path / "bsp_drops"
    drop.mkdir()
    return BSPIndiaConfig(
        agent_iata_code="12345678",
        username="test_user",
        password="test_password",
        file_source_dir=str(drop),
    )


@pytest.fixture
def file_source_dir(bsp_config: BSPIndiaConfig) -> Path:
    return Path(bsp_config.file_source_dir)


@pytest_asyncio.fixture
async def bsp_driver(bsp_config: BSPIndiaConfig, tenant_id: str):
    drv = BSPIndiaDriver(bsp_config, tenant_id=tenant_id)
    try:
        yield drv
    finally:
        await drv.aclose()


# Re-export private builders for tests that want to compose malformed
# records. Not part of the driver's public surface.
__all__ = [
    "LINE_LENGTH",
    "_bfh01",
    "_bft99",
    "_bks24",
    "_bks39",
    "_bks45",
    "_memo",
    "_pad_right",
]
