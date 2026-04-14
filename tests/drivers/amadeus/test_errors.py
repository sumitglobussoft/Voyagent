"""Error-path tests for :class:`AmadeusDriver`.

The main ``test_driver.py`` covers happy paths plus a handful of status
code mappings (401 / 429 / 503). This module adds:

  * a plain 4xx (400 without a validation-shaped code, 404) mapped to
    concrete :class:`DriverError` subclasses — never a raw
    :class:`httpx.HTTPStatusError`,
  * a 2xx with a malformed JSON body — currently a gap in the driver's
    error surface, tracked via ``xfail``.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from drivers._contracts.errors import (
    DriverError,
    NotFoundError,
    PermanentError,
    ValidationFailedError,
)
from drivers._contracts.fare_search import FareSearchCriteria
from drivers.amadeus.driver import AmadeusDriver
from schemas.canonical import PassengerType
from datetime import date


pytestmark = pytest.mark.asyncio


def _criteria() -> FareSearchCriteria:
    return FareSearchCriteria(
        passengers={PassengerType.ADULT: 1},
        origin="BOM",
        destination="DXB",
        outbound_date=date(2026, 5, 10),
    )


# --------------------------------------------------------------------------- #
# 4xx mappings                                                                #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_400_validation_maps_to_validation_failed(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(
            400,
            json={
                "errors": [
                    {
                        "code": 477,
                        "title": "INVALID FORMAT",
                        "detail": "origin must be 3-letter IATA",
                    }
                ]
            },
        )
    )

    with pytest.raises(ValidationFailedError) as exc:
        await amadeus_driver.search(_criteria())
    # Never leak httpx status-error types.
    assert isinstance(exc.value, DriverError)
    assert "INVALID" in str(exc.value) or "format" in str(exc.value).lower()


@respx.mock
async def test_read_404_maps_to_not_found(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v1/booking/flight-orders/unknown-id").mock(
        return_value=httpx.Response(
            404,
            json={"errors": [{"code": 1797, "title": "NOT FOUND"}]},
        )
    )

    with pytest.raises(NotFoundError):
        await amadeus_driver.read("unknown-id")


@respx.mock
async def test_search_418_maps_to_generic_permanent_error_not_raw_httperror(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    """An unusual 4xx must still become a DriverError, not an httpx error."""
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(418, json={"errors": [{"title": "IM A TEAPOT"}]})
    )
    with pytest.raises(DriverError):
        await amadeus_driver.search(_criteria())


# --------------------------------------------------------------------------- #
# Malformed JSON response                                                     #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_200_with_malformed_body_raises_driver_error(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, content=b"not-json-at-all <html>")
    )

    with pytest.raises(PermanentError) as exc:
        await amadeus_driver.search(_criteria())
    # Driver-hierarchy exception, not raw json.JSONDecodeError.
    assert isinstance(exc.value, DriverError)
    # Status code is preserved in the message / vendor_ref for debugging.
    assert "200" in str(exc.value) or "200" in (exc.value.vendor_ref or "")
    # Body preview is included so operators can triage without a capture.
    assert "not-json" in str(exc.value)


# --------------------------------------------------------------------------- #
# Negative: a well-formed 200 still works                                     #
# --------------------------------------------------------------------------- #


@respx.mock
async def test_search_200_with_valid_json_still_parses(
    amadeus_driver: AmadeusDriver,
    sample_token_response: dict,
) -> None:
    """Regression guard: the JSON-decode guard must not break valid 2xx bodies."""
    base = amadeus_driver._config.api_base.rstrip("/")
    respx.post(f"{base}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json=sample_token_response)
    )
    respx.get(f"{base}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"count": 0}})
    )
    # No exception; empty offers is a legitimate result shape.
    result = await amadeus_driver.search(_criteria())
    assert result == [] or result is not None
