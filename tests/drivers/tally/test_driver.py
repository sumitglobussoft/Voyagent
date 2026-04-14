"""Integration-style tests for :class:`TallyDriver` using ``respx``."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
import respx

from drivers._contracts.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    ConflictError,
    PermanentError,
    ValidationFailedError,
)
from drivers.tally.driver import TallyDriver
from schemas.canonical import (
    JournalEntry,
    JournalLine,
    LocalizedText,
    Money,
)

pytestmark = pytest.mark.asyncio


def _uuid7() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _balanced_entry(tenant: str) -> JournalEntry:
    cash_id = "00000000-0000-7000-8000-000000000005"
    sales_id = "00000000-0000-7000-8000-000000000002"
    now = datetime.now(timezone.utc)
    return JournalEntry(
        id=_uuid7(),
        tenant_id=tenant,
        entry_date=date(2026, 4, 14),
        narration=LocalizedText(default="Daily cash sale"),
        lines=[
            JournalLine(account_id=cash_id, debit=Money(amount=Decimal("500"), currency="INR")),
            JournalLine(account_id=sales_id, credit=Money(amount=Decimal("500"), currency="INR")),
        ],
        source_event="test",
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# manifest                                                                    #
# --------------------------------------------------------------------------- #


async def test_manifest_declares_expected_capabilities(tally_driver: TallyDriver) -> None:
    m = tally_driver.manifest()
    assert m.driver == "tally"
    assert m.version == TallyDriver.version
    assert m.implements == ["AccountingDriver"]
    assert m.capabilities["list_accounts"] == "full"
    assert m.capabilities["post_journal"] == "supported_via_xml_import"
    assert m.capabilities["create_invoice"] == "supported_via_xml_import"
    assert m.capabilities["read_invoice"] == "not_supported"
    assert m.capabilities["read_account_balance"] == "partial"
    assert "http_xml" in m.transport
    assert "desktop_host" in m.requires
    assert "tenant_credentials" in m.requires
    # JSON Schema sanity.
    assert m.tenant_config_schema["required"] == ["company_name"]


# --------------------------------------------------------------------------- #
# list_accounts                                                               #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_list_accounts_happy_path(
    tally_driver: TallyDriver,
    sample_ping_response: bytes,
    sample_ledger_list_response: bytes,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    # respx intercepts in order of registration; a single POST route returning
    # different bodies on sequential calls keeps the test readable.
    route = respx.post(f"{base}/").mock(
        side_effect=[
            httpx.Response(200, content=sample_ping_response),
            httpx.Response(200, content=sample_ledger_list_response),
        ]
    )
    accounts = await tally_driver.list_accounts()
    assert route.call_count == 2
    assert len(accounts) >= 5
    # The sample contains one known unknown parent; it must still produce a row.
    assert any(a.code == "Mystery Ledger" for a in accounts)


@respx.mock
async def test_list_accounts_401_raises_authentication_error(
    tally_driver: TallyDriver,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    respx.post(f"{base}/").mock(return_value=httpx.Response(401, content=b"unauthorised"))
    with pytest.raises(AuthenticationError):
        await tally_driver.list_accounts()


@respx.mock
async def test_list_accounts_malformed_xml_raises_validation_failed(
    tally_driver: TallyDriver,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    respx.post(f"{base}/").mock(return_value=httpx.Response(200, content=b"not xml at all"))
    with pytest.raises((ValidationFailedError, PermanentError)):
        await tally_driver.list_accounts()


# --------------------------------------------------------------------------- #
# post_journal                                                                #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_post_journal_happy_path(
    tally_driver: TallyDriver,
    sample_voucher_create_response: bytes,
    tenant_id: str,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    respx.post(f"{base}/").mock(
        return_value=httpx.Response(200, content=sample_voucher_create_response)
    )
    canonical_id = await tally_driver.post_journal(_balanced_entry(tenant_id))
    # Canonical EntityId shape (uuid v7-ish, lowercase, hyphenated).
    assert len(canonical_id) == 36
    # Correlation captured.
    assert tally_driver.recent_voucher_ids.get(canonical_id) == "12345"


@respx.mock
async def test_post_journal_lineerror_maps_to_permanent_error(
    tally_driver: TallyDriver,
    sample_error_response: bytes,
    tenant_id: str,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    respx.post(f"{base}/").mock(
        return_value=httpx.Response(200, content=sample_error_response)
    )
    with pytest.raises(PermanentError) as exc:
        await tally_driver.post_journal(_balanced_entry(tenant_id))
    assert "totals do not match" in str(exc.value).lower()


@respx.mock
async def test_post_journal_company_not_open_maps_to_conflict(
    tally_driver: TallyDriver,
    sample_company_not_open_response: bytes,
    tenant_id: str,
) -> None:
    base = tally_driver._config.gateway_url.rstrip("/")
    respx.post(f"{base}/").mock(
        return_value=httpx.Response(200, content=sample_company_not_open_response)
    )
    with pytest.raises(ConflictError) as exc:
        await tally_driver.post_journal(_balanced_entry(tenant_id))
    assert "not open" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# read_invoice                                                                #
# --------------------------------------------------------------------------- #


async def test_read_invoice_is_not_supported(tally_driver: TallyDriver) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await tally_driver.read_invoice("00000000-0000-7000-8000-000000000099")


# --------------------------------------------------------------------------- #
# read_account_balance                                                        #
# --------------------------------------------------------------------------- #


async def test_read_account_balance_raises_capability_not_supported(
    tally_driver: TallyDriver,
) -> None:
    with pytest.raises(CapabilityNotSupportedError):
        await tally_driver.read_account_balance(
            "00000000-0000-7000-8000-000000000005", date(2024, 1, 1)
        )


async def test_read_account_balance_future_date_still_raises(
    tally_driver: TallyDriver,
) -> None:
    # Future as-of is explicitly not supported in v0.
    with pytest.raises(CapabilityNotSupportedError):
        await tally_driver.read_account_balance(
            "00000000-0000-7000-8000-000000000005", date(2030, 12, 31)
        )
