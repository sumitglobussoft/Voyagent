"""Shared fixtures for the Tally driver test suite.

Uses ``respx`` to intercept httpx traffic; tests never hit a real Tally
Gateway. Configuration defaults to a non-routable host so a misconfigured
CI job can never accidentally reach a live Tally.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
import pytest_asyncio

from drivers.tally.config import TallyConfig
from drivers.tally.driver import TallyDriver


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
def tally_config() -> TallyConfig:
    """In-memory, env-independent config pinned to a non-routable host.

    ``localtest.me`` is a convenient IANA-reserved-ish domain that resolves
    to loopback — combined with respx intercept, requests never leave the
    test process.
    """
    return TallyConfig(
        gateway_url="http://tally.localtest.me:9000",
        company_name="Test Travel Agency Pvt Ltd",
        timeout_seconds=5.0,
        max_retries=1,
    )


@pytest.fixture
def ledger_name_resolver() -> Callable[[str], str]:
    """Resolver that maps a handful of canonical ids to Tally display names.

    Tests assemble canonical records with these ids so the driver's
    posting methods can translate them into Tally's name-keyed world
    without touching a real database.
    """
    mapping = {
        "00000000-0000-7000-8000-000000000001": "Sundry Debtors - Acme Ltd",
        "00000000-0000-7000-8000-000000000002": "Sales - Domestic",
        "00000000-0000-7000-8000-000000000003": "Duties & Taxes - CGST",
        "00000000-0000-7000-8000-000000000004": "Duties & Taxes - SGST",
        "00000000-0000-7000-8000-000000000005": "Cash-in-hand",
        "00000000-0000-7000-8000-000000000006": "Bank Accounts - HDFC",
    }

    def resolve(entity_id: str) -> str:
        try:
            return mapping[entity_id]
        except KeyError:
            raise KeyError(f"unknown ledger {entity_id}") from None

    return resolve


@pytest_asyncio.fixture
async def tally_driver(
    tally_config: TallyConfig,
    tenant_id: str,
    ledger_name_resolver: Callable[[str], str],
):
    driver = TallyDriver(
        tally_config,
        tenant_id=tenant_id,
        ledger_name_resolver=ledger_name_resolver,
    )
    try:
        yield driver
    finally:
        await driver.aclose()


# --------------------------------------------------------------------------- #
# Recorded-sample XML bodies                                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture
def sample_ping_response() -> bytes:
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<ENVELOPE>"
        b"<HEADER><VERSION>1</VERSION></HEADER>"
        b"<BODY>"
        b"<DATA>"
        b"<COMPANYNAME>Test Travel Agency Pvt Ltd</COMPANYNAME>"
        b"<BOOKSFROM>20240401</BOOKSFROM>"
        b"<BASECURRENCYSYMBOL>INR</BASECURRENCYSYMBOL>"
        b"</DATA>"
        b"</BODY>"
        b"</ENVELOPE>"
    )


@pytest.fixture
def sample_ledger_list_response() -> bytes:
    """A small chart of accounts covering one ledger per AccountType branch."""
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<ENVELOPE>"
        b"<BODY><DATA><COLLECTION>"
        # Asset
        b"<LEDGER NAME=\"Cash\">"
        b"<NAME>Cash</NAME>"
        b"<PARENT>Cash-in-hand</PARENT>"
        b"<OPENINGBALANCE>1500.00 Dr</OPENINGBALANCE>"
        b"<CURRENCYSYMBOL>INR</CURRENCYSYMBOL>"
        b"</LEDGER>"
        # Liability
        b"<LEDGER NAME=\"CGST Payable\">"
        b"<PARENT>Duties &amp; Taxes</PARENT>"
        b"<OPENINGBALANCE>0.00</OPENINGBALANCE>"
        b"</LEDGER>"
        # Equity
        b"<LEDGER NAME=\"Proprietor Capital\">"
        b"<PARENT>Capital Account</PARENT>"
        b"<OPENINGBALANCE>500000.00 Cr</OPENINGBALANCE>"
        b"</LEDGER>"
        # Income
        b"<LEDGER NAME=\"Sales - Domestic\">"
        b"<PARENT>Sales Accounts</PARENT>"
        b"</LEDGER>"
        # Expense
        b"<LEDGER NAME=\"Office Rent\">"
        b"<PARENT>Indirect Expenses</PARENT>"
        b"</LEDGER>"
        # Unknown parent — must fall back to EXPENSE + WARNING.
        b"<LEDGER NAME=\"Mystery Ledger\">"
        b"<PARENT>Some Custom Group</PARENT>"
        b"</LEDGER>"
        b"</COLLECTION></DATA></BODY>"
        b"</ENVELOPE>"
    )


@pytest.fixture
def sample_ledger_list_large() -> bytes:
    """~20 ledgers covering a wider chart, for pagination-shape tests."""
    pieces = [b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ENVELOPE><BODY><DATA><COLLECTION>"]
    sample_parents = [
        "Cash-in-hand",
        "Bank Accounts",
        "Sundry Debtors",
        "Fixed Assets",
        "Sundry Creditors",
        "Duties & Taxes",
        "Loans (Liability)",
        "Capital Account",
        "Sales Accounts",
        "Direct Incomes",
        "Indirect Incomes",
        "Purchase Accounts",
        "Direct Expenses",
        "Indirect Expenses",
        "Current Assets",
        "Current Liabilities",
        "Investments",
        "Provisions",
        "Reserves & Surplus",
        "Stock-in-hand",
    ]
    for i, parent in enumerate(sample_parents):
        escaped_parent = parent.replace("&", "&amp;")
        pieces.append(
            (
                f"<LEDGER NAME=\"Ledger {i:02d}\">"
                f"<PARENT>{escaped_parent}</PARENT>"
                f"<OPENINGBALANCE>{i * 100}.00</OPENINGBALANCE>"
                f"</LEDGER>"
            ).encode()
        )
    pieces.append(b"</COLLECTION></DATA></BODY></ENVELOPE>")
    return b"".join(pieces)


@pytest.fixture
def sample_voucher_create_response() -> bytes:
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<RESPONSE>"
        b"<CREATED>1</CREATED>"
        b"<ALTERED>0</ALTERED>"
        b"<DELETED>0</DELETED>"
        b"<LASTVCHID>12345</LASTVCHID>"
        b"</RESPONSE>"
    )


@pytest.fixture
def sample_error_response() -> bytes:
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<RESPONSE>"
        b"<LINEERROR>Voucher Totals do not match</LINEERROR>"
        b"</RESPONSE>"
    )


@pytest.fixture
def sample_company_not_open_response() -> bytes:
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<RESPONSE>"
        b"<LINEERROR>Company 'Test Travel Agency Pvt Ltd' not open</LINEERROR>"
        b"</RESPONSE>"
    )
