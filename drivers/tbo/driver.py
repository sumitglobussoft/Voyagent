"""The TBO driver — satisfies :class:`HotelSearchDriver` + :class:`HotelBookingDriver`.

TBO (Travel Boutique Online) is a hotel aggregator widely used by
Indian travel agencies. Its public Hotels REST API documents POST
verbs under ``/Search``, ``/PreBook``, ``/Book``, etc. — exact URLs
vary by partner onboarding. The driver here wires the real HTTP
shape for search and rate-check so credentials can be dropped in later;
booking verbs honestly raise :class:`CapabilityNotSupportedError` until
we can exercise them against a live sandbox.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation as decimal_InvalidOperation
from typing import Any, ClassVar

from pydantic import ValidationError

from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    PermanentError,
    ValidationFailedError,
)
from drivers._contracts.hotel_search import HotelOffer, HotelSearchCriteria
from drivers._contracts.manifest import CapabilityManifest
from schemas.canonical import (
    BoardBasis,
    EntityId,
    HotelBooking,
    HotelProperty,
    HotelRate,
    HotelRoom,
    HotelSearchResult,
    HotelStay,
    LocalizedText,
    Money,
)

from .client import TBOClient
from .config import TBOConfig
from .errors import DRIVER_NAME
from .manifest import build_manifest

logger = logging.getLogger(__name__)

# Endpoint paths are partner-specific; we centralize the constants so a
# tenant override only touches one file when TBO moves things around.
_SEARCH_PATH = "/Search"
_PREBOOK_PATH = "/PreBook"
_BOOK_PATH = "/Book"
_CANCEL_PATH = "/Cancel"
_BOOKING_DETAIL_PATH = "/BookingDetail"


class TBODriver:
    """Reference driver for the TBO Hotels REST API.

    Construction raises :class:`PermanentError` when credentials are
    missing — the orchestrator surfaces that as "no hotel driver
    configured for this tenant", matching the ticketing_visa failure
    mode when Amadeus credentials are absent.
    """

    name: ClassVar[str] = "tbo"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        config: TBOConfig,
        *,
        client: TBOClient | None = None,
        tenant_id: EntityId | None = None,
    ) -> None:
        if not config.username or not config.password.get_secret_value():
            raise PermanentError(
                DRIVER_NAME,
                "TBO credentials missing: set VOYAGENT_TBO_USERNAME and "
                "VOYAGENT_TBO_PASSWORD (or supply tenant credentials).",
            )
        self._config = config
        self._client = client or TBOClient(config)
        self._tenant_id = tenant_id

    async def aclose(self) -> None:
        await self._client.aclose()

    def manifest(self) -> CapabilityManifest:
        return build_manifest(self.version)

    # ------------------------------------------------------------------ #
    # HotelSearchDriver                                                  #
    # ------------------------------------------------------------------ #

    async def search(self, criteria: HotelSearchCriteria) -> list[HotelOffer]:
        """Shop TBO availability for ``criteria`` and return driver-layer offers.

        TBO's search returns a nested HotelResults payload; we
        translate the minimum set of fields into :class:`HotelOffer`
        records. Not every TBO rate exposes a stable cancellation
        policy, so the cancellation text falls back to a generic
        string when absent.
        """
        payload = _build_search_payload(criteria)
        raw = await self._client.post_json(_SEARCH_PATH, json=payload)
        return _parse_search_offers(raw)

    async def search_results(
        self, criteria: HotelSearchCriteria
    ) -> list[HotelSearchResult]:
        """Structured variant of :meth:`search` returning canonical results.

        The tool layer prefers this shape because :class:`HotelSearchResult`
        carries the property + rates together, which maps cleanly to the
        LLM-facing summary.
        """
        payload = _build_search_payload(criteria)
        raw = await self._client.post_json(_SEARCH_PATH, json=payload)
        return _parse_search_results(raw, criteria)

    async def check_rate(self, rate_key: str) -> HotelRate:
        """Re-price a shopped rate via TBO's PreBook verb.

        Rate-check is idempotent; TBO returns the current price + a
        possibly-refreshed rate token.
        """
        if not rate_key:
            raise ValidationFailedError(
                DRIVER_NAME, "check_rate requires a non-empty rate_key."
            )
        raw = await self._client.post_json(
            _PREBOOK_PATH, json={"BookingCode": rate_key}
        )
        return _parse_rate(raw)

    # ------------------------------------------------------------------ #
    # HotelBookingDriver                                                 #
    # ------------------------------------------------------------------ #

    async def book(self, offer_ref: str, stay: HotelStay) -> HotelBooking:
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "tbo.book: needs real credentials — see manifest. The v0 "
            "driver ships search + check_rate wiring only; booking will "
            "land once a TBO sandbox account is onboarded.",
        )

    async def cancel(self, booking_id: EntityId) -> HotelBooking:
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "tbo.cancel: needs real credentials — see manifest.",
        )

    async def read(self, booking_id: EntityId) -> HotelBooking:
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "tbo.read: needs real credentials — see manifest.",
        )


# --------------------------------------------------------------------------- #
# Payload helpers                                                             #
# --------------------------------------------------------------------------- #


def _build_search_payload(criteria: HotelSearchCriteria) -> dict[str, Any]:
    """Build the JSON body TBO expects for ``/Search``.

    Field names follow the public TBO Hotels API documentation. Live
    tenants may need extra fields (``ResponseTime``, ``IsDetailedResponse``,
    ``PreferredCurrency`` …); those are partner-specific.
    """
    return {
        "CheckIn": criteria.check_in.isoformat(),
        "CheckOut": criteria.check_out.isoformat(),
        "HotelCodes": "",  # empty -> search by city / country
        "GuestNationality": criteria.destination_country,
        "PaxRooms": [
            {
                "Adults": max(1, criteria.guest_count),
                "Children": 0,
                "ChildrenAges": [],
            }
        ],
        "CityCode": criteria.destination_city,
        "CountryCode": criteria.destination_country,
        "IsDetailedResponse": True,
        "ResponseTime": 15,
        "Filters": {},
    }


def _parse_search_offers(raw: Any) -> list[HotelOffer]:
    """Map a TBO search response into driver-layer :class:`HotelOffer` records."""
    if not isinstance(raw, dict):
        return []
    hotels = (raw.get("HotelSearchResult") or {}).get("HotelResults") or []
    offers: list[HotelOffer] = []
    for h in hotels:
        hotel_id = str(h.get("HotelCode") or "")
        raw_country = h.get("CountryCode")
        # Only accept a clean 2-letter upper ISO-alpha-2 country code. Anything
        # else (1-letter, 3-letter, empty, None, mixed case like "ind") is a
        # vendor data-quality miss; fabricating "XX" would poison the offer.
        if not (isinstance(raw_country, str) and len(raw_country) == 2 and raw_country.isalpha()):
            logger.debug(
                "tbo._parse_search_offers: skipping offer with bad CountryCode %r (hotel_id=%r)",
                raw_country,
                hotel_id,
            )
            continue
        country = raw_country.upper()
        name = str(h.get("HotelName") or "Unknown hotel")
        rates = h.get("Rooms") or []
        first_rate = rates[0] if rates else {}
        price_total = first_rate.get("TotalFare") or first_rate.get("Price") or 0
        currency = (
            first_rate.get("Currency")
            or raw.get("Currency")
            or "USD"
        )
        try:
            cost = Money(amount=Decimal(str(price_total)), currency=str(currency))
            offer = HotelOffer(
                property_name=name,
                property_ref=hotel_id,
                address_country=country,
                cost=cost,
                board_type=str(first_rate.get("MealType") or "room_only"),
                room_type=str(first_rate.get("Name") or first_rate.get("RoomType") or ""),
                cancellation_text=LocalizedText(
                    default=str(
                        first_rate.get("CancellationPolicy")
                        or "See supplier cancellation terms."
                    )
                ),
                offer_ref=str(first_rate.get("BookingCode") or h.get("HotelCode") or ""),
            )
        except (ValidationError, ValueError, decimal_InvalidOperation) as exc:
            logger.debug(
                "tbo._parse_search_offers: skipping offer (hotel_id=%r, currency=%r, price=%r): %s",
                hotel_id,
                currency,
                price_total,
                exc,
            )
            continue
        offers.append(offer)
    return offers


def _parse_search_results(
    raw: Any, criteria: HotelSearchCriteria
) -> list[HotelSearchResult]:
    """Map a TBO search response into canonical :class:`HotelSearchResult`."""
    if not isinstance(raw, dict):
        return []
    hotels = (raw.get("HotelSearchResult") or {}).get("HotelResults") or []
    results: list[HotelSearchResult] = []
    for h in hotels:
        country = str(h.get("CountryCode") or "XX").upper()[:2] or "XX"
        prop = HotelProperty(
            id=str(h.get("HotelCode") or ""),
            name=str(h.get("HotelName") or "Unknown hotel"),
            address=h.get("Address"),
            city=str(h.get("CityName") or criteria.destination_city),
            country=country,
            latitude=_maybe_float(h.get("Latitude")),
            longitude=_maybe_float(h.get("Longitude")),
            star_rating=_maybe_int(h.get("HotelRating") or h.get("StarRating")),
            amenities=list(h.get("HotelFacilities") or []),
            images=[str(u) for u in (h.get("Images") or [])],
        )
        rates: list[HotelRate] = []
        for r in h.get("Rooms") or []:
            rate = _parse_rate_entry(r, raw.get("Currency"))
            if rate is not None:
                rates.append(rate)
        if not rates:
            continue
        results.append(
            HotelSearchResult(
                property=prop,
                rates=rates,
                check_in=criteria.check_in,
                check_out=criteria.check_out,
                guest_count=criteria.guest_count,
            )
        )
    return results


def _parse_rate_entry(r: dict[str, Any], fallback_currency: Any) -> HotelRate | None:
    price_total = r.get("TotalFare") or r.get("Price")
    if price_total is None:
        return None
    currency = r.get("Currency") or fallback_currency or "USD"
    try:
        price = Money(amount=Decimal(str(price_total)), currency=str(currency))
    except Exception:
        return None
    room = HotelRoom(
        code=str(r.get("RoomTypeCode") or r.get("RoomTypeId") or "ROOM"),
        name=str(r.get("Name") or r.get("RoomType") or "Room"),
        board_basis=_parse_board_basis(r.get("MealType")),
        max_occupancy=int(r.get("MaxOccupancy") or 2),
        bed_type=r.get("BedType"),
    )
    cancel_text = r.get("CancellationPolicy")
    return HotelRate(
        room=room,
        price=price,
        cancellation_policy=(
            LocalizedText(default=str(cancel_text)) if cancel_text else None
        ),
        is_refundable=bool(r.get("IsRefundable", False)),
        rate_key=str(r.get("BookingCode") or ""),
    )


def _parse_rate(raw: Any) -> HotelRate:
    if not isinstance(raw, dict):
        raise ValidationFailedError(
            DRIVER_NAME, f"PreBook returned non-object payload: {raw!r}"
        )
    body = raw.get("PreBookResult") or raw
    rooms = body.get("Rooms") or []
    if not rooms:
        raise ValidationFailedError(
            DRIVER_NAME, "PreBook response contained no Rooms."
        )
    rate = _parse_rate_entry(rooms[0], body.get("Currency"))
    if rate is None:
        raise ValidationFailedError(
            DRIVER_NAME, "PreBook response Room did not price cleanly."
        )
    return rate


def _parse_board_basis(raw: Any) -> BoardBasis:
    if not raw:
        return BoardBasis.RO
    token = str(raw).strip().lower()
    mapping = {
        "room only": BoardBasis.RO,
        "room_only": BoardBasis.RO,
        "ro": BoardBasis.RO,
        "breakfast": BoardBasis.BB,
        "bed and breakfast": BoardBasis.BB,
        "bb": BoardBasis.BB,
        "half board": BoardBasis.HB,
        "hb": BoardBasis.HB,
        "full board": BoardBasis.FB,
        "fb": BoardBasis.FB,
        "all inclusive": BoardBasis.AI,
        "ai": BoardBasis.AI,
    }
    return mapping.get(token, BoardBasis.RO)


def _maybe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(v: Any) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


__all__ = ["TBODriver"]
