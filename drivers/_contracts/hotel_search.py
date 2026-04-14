"""HotelSearchDriver — shopping hotel availability and rates.

`HotelOffer` is a driver-layer type, not canonical. The agent selects an
offer, then the `HotelBookingDriver.book` call converts it into a canonical
`HotelStay` + `HotelBooking` pair at confirmation time.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.canonical import CountryCode, LocalizedText, Money

from .base import Driver


def _driver_type_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class HotelSearchCriteria(BaseModel):
    """Inputs to a hotel search.

    Destination is expressed as country + city in v0; structured geocoding
    (lat/lng, radius, POI anchors) is deferred until a geo service lands.
    """

    model_config = _driver_type_config()

    destination_country: CountryCode
    destination_city: str
    check_in: date
    check_out: date
    guest_count: int = Field(ge=1)
    budget_min: Money | None = Field(
        default=None,
        description="Optional lower bound on per-stay cost. Driver filters before returning.",
    )
    budget_max: Money | None = Field(
        default=None,
        description="Optional upper bound on per-stay cost. Driver filters before returning.",
    )

    @model_validator(mode="after")
    def _validate(self) -> HotelSearchCriteria:
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in.")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min.currency != self.budget_max.currency:
                raise ValueError("budget_min and budget_max must share a currency.")
            if self.budget_min.amount > self.budget_max.amount:
                raise ValueError("budget_min must not exceed budget_max.")
        return self


class HotelOffer(BaseModel):
    """A shoppable hotel offer returned by a driver.

    Driver-layer type. Persistence happens only after `HotelBookingDriver.book`
    converts a selected offer into canonical `HotelStay` + `HotelBooking`.
    """

    model_config = _driver_type_config()

    property_name: str
    property_ref: str = Field(description="Driver-local hotel identifier.")
    address_country: CountryCode
    cost: Money = Field(description="Total stay cost across all nights and guests.")
    board_type: str = Field(description="Free-form in v0: 'BB', 'HB', 'FB', 'AI', 'room_only'.")
    room_type: str
    cancellation_text: LocalizedText = Field(
        description="Cancellation policy as localized text. Structured policies arrive in v1.",
    )
    offer_ref: str = Field(
        description="Vendor-local offer identifier used when booking. Opaque to the agent.",
    )


@runtime_checkable
class HotelSearchDriver(Driver, Protocol):
    """Search hotel availability against a bedbank, DMC, or property direct."""

    async def search(self, criteria: HotelSearchCriteria) -> list[HotelOffer]:
        """Return hotel offers matching `criteria`.

        Side effects: none (read-only shopping).
        Idempotent: yes; availability and pricing may drift between calls.

        Raises:
            AuthenticationError, AuthorizationError, RateLimitError,
            TransientError, PermanentError, ValidationFailedError,
            UpstreamTimeoutError.
        """
        ...


__all__ = ["HotelOffer", "HotelSearchCriteria", "HotelSearchDriver"]
