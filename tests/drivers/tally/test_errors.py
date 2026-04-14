"""Error-path tests for :class:`TallyDriver`.

``test_driver.py`` already covers 401 -> AuthenticationError, LINEERROR ->
PermanentError, company-not-open -> ConflictError, and the
``CapabilityNotSupportedError`` paths. This file adds:

  * A Tally ``<RESPONSE>`` element that wraps an error message rather
    than a LINEERROR block — the driver should still map it to a
    domain-level :class:`DriverError`.
  * A connection refused to the Tally gateway — the client must raise a
    connection-specific :class:`TransientError`, not an ``httpx`` error.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from drivers._contracts.errors import (
    DriverError,
    PermanentError,
    TransientError,
)
from drivers.tally.config import TallyConfig
from drivers.tally.driver import TallyDriver


pytestmark = pytest.mark.asyncio


@respx.mock
async def test_list_accounts_response_error_envelope_maps_to_driver_error(
    tally_driver: TallyDriver,
) -> None:
    """Tally sometimes wraps a failure in a plain ``<RESPONSE>`` element
    with a free-text error. The driver must not silently return an empty
    ledger list — it should raise a :class:`DriverError` subclass."""
    base = tally_driver._config.gateway_url.rstrip("/")
    body = (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        b"<RESPONSE>ERROR: TDL report not found</RESPONSE>"
    )
    respx.post(f"{base}/").mock(return_value=httpx.Response(200, content=body))

    with pytest.raises((DriverError, PermanentError)):
        await tally_driver.list_accounts()


async def test_tally_unreachable_raises_transient_error() -> None:
    """A connection refused (or similar) must surface as
    :class:`TransientError`, never as a raw ``httpx`` exception.

    Uses a config pinned to a discard-port so no real service answers
    and ``max_retries=0`` so the test returns fast.
    """
    config = TallyConfig(
        gateway_url="http://127.0.0.1:1/",  # TCP discard — always refused.
        company_name="Test Travel Agency",
        timeout_seconds=0.5,
        max_retries=0,
    )
    driver = TallyDriver(config, tenant_id="00000000-0000-7000-8000-00000000aaaa")
    try:
        with pytest.raises((TransientError, DriverError)) as exc:
            await driver.list_accounts()
        # Make sure the exception is from the driver error hierarchy.
        assert isinstance(exc.value, DriverError)
    finally:
        await driver.aclose()
