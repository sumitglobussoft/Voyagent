"""BSPIndiaDriver integration-ish tests.

These tests read HAF files from a temp ``file_source_dir`` rather than
hitting the network — respx is not needed. They exercise the driver's
manifest, fetch_statement happy path, country-enforcement, and the
not-supported stubs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    NotFoundError,
    ValidationFailedError,
)
from drivers.bsp_india.driver import BSPIndiaDriver
from schemas.canonical import LocalizedText, Period


pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# manifest                                                                    #
# --------------------------------------------------------------------------- #


async def test_manifest_declares_file_local_transport_when_drop_dir_set(
    bsp_driver: BSPIndiaDriver,
) -> None:
    m = bsp_driver.manifest()
    assert m.driver == "bsp_india"
    assert m.implements == ["BSPDriver"]
    assert m.capabilities["fetch_statement"] == "full"
    assert m.capabilities["raise_adm"] == "not_supported"
    assert m.capabilities["raise_acm"] == "not_supported"
    assert m.capabilities["make_settlement_payment"] == "not_supported"
    assert "file_local" in m.transport
    assert "tenant_credentials" in m.requires
    assert m.tenant_config_schema["required"] == ["agent_iata_code"]


async def test_manifest_marks_fetch_not_supported_without_drop_dir() -> None:
    from drivers.bsp_india.config import BSPIndiaConfig

    cfg = BSPIndiaConfig(agent_iata_code="12345678", file_source_dir=None)
    drv = BSPIndiaDriver(cfg)
    try:
        m = drv.manifest()
        assert m.capabilities["fetch_statement"] == "not_supported"
        assert "http" in m.transport
    finally:
        await drv.aclose()


# --------------------------------------------------------------------------- #
# fetch_statement                                                             #
# --------------------------------------------------------------------------- #


async def test_fetch_statement_happy_path_reads_file_and_produces_report(
    bsp_driver: BSPIndiaDriver,
    file_source_dir: Path,
    sample_haf_bytes: bytes,
) -> None:
    # Matches the convention the client expects.
    target = file_source_dir / "HAF_12345678_20260401_20260415.txt"
    target.write_bytes(sample_haf_bytes)

    period = Period(
        start=datetime(2026, 4, 1, tzinfo=timezone.utc),
        # Half-open: end is the day after period_end inclusive.
        end=datetime(2026, 4, 16, tzinfo=timezone.utc),
    )
    report = await bsp_driver.fetch_statement("IN", period)
    assert report.country == "IN"
    assert len(report.transactions) == 6
    assert report.source_ref == "HAF_12345678_20260401_20260415"


async def test_fetch_statement_rejects_non_in_country(bsp_driver: BSPIndiaDriver) -> None:
    period = Period(
        start=datetime(2026, 4, 1, tzinfo=timezone.utc),
        end=datetime(2026, 4, 16, tzinfo=timezone.utc),
    )
    with pytest.raises(ValidationFailedError) as exc:
        await bsp_driver.fetch_statement("AE", period)
    assert "only services in" in str(exc.value).lower()
    assert "country=ae" in str(exc.value).lower()


async def test_fetch_statement_missing_file_raises_not_found(
    bsp_driver: BSPIndiaDriver,
) -> None:
    period = Period(
        start=datetime(2026, 4, 1, tzinfo=timezone.utc),
        end=datetime(2026, 4, 16, tzinfo=timezone.utc),
    )
    with pytest.raises(NotFoundError):
        await bsp_driver.fetch_statement("IN", period)


# --------------------------------------------------------------------------- #
# not-supported stubs                                                         #
# --------------------------------------------------------------------------- #


async def test_raise_adm_not_supported(bsp_driver: BSPIndiaDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await bsp_driver.raise_adm("REF-1", LocalizedText(default="dispute"))


async def test_raise_acm_not_supported(bsp_driver: BSPIndiaDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await bsp_driver.raise_acm("REF-1", LocalizedText(default="credit"))


async def test_make_settlement_payment_not_supported(bsp_driver: BSPIndiaDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await bsp_driver.make_settlement_payment("01900000-0000-7000-8000-000000000001")
