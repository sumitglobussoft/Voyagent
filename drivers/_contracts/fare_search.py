"""FareSearchDriver — flight/fare shopping across GDS, NDC, and aggregators."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.canonical import (
    CabinClass,
    Fare,
    IATACode,
    Money,
    PassengerType,
)

from .base import Driver


def _driver_type_config() -> ConfigDict:
    """Mirror of canonical `_strict()` for driver-layer helper types."""
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class FareSearchCriteria(BaseModel):
    """Inputs to a fare search.

    Driver-layer helper type — not a canonical model. The agent builds this
    from an `Enquiry`; the driver translates into vendor-specific shopping
    queries (Amadeus SOAP Shopping, Sabre BargainFinderMax, NDC ShoppingRQ).
    """

    model_config = _driver_type_config()

    passengers: dict[PassengerType, int] = Field(
        description="Passenger counts by type. At least one passenger required in total.",
    )
    origin: IATACode
    destination: IATACode
    outbound_date: date
    return_date: date | None = Field(
        default=None,
        description="Omit for one-way. Must be on or after outbound_date for round-trip.",
    )
    cabin: CabinClass = CabinClass.ECONOMY
    direct_only: bool = False
    airline_whitelist: list[IATACode] = Field(
        default_factory=list,
        description="If non-empty, only fares marketed by these airlines are acceptable.",
    )
    airline_blacklist: list[IATACode] = Field(
        default_factory=list,
        description="Fares marketed by these airlines are excluded.",
    )
    max_price: Money | None = Field(
        default=None,
        description="Hard upper bound on total fare. Driver filters before returning.",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=250,
        description=(
            "Maximum number of offers the driver should return. Defaults to "
            "50; the ceiling of 250 reflects the Amadeus Self-Service hard "
            "cap. Other drivers should honour the value within their own "
            "vendor constraints."
        ),
    )

    @model_validator(mode="after")
    def _validate(self) -> FareSearchCriteria:
        total_pax = sum(self.passengers.values())
        if total_pax < 1:
            raise ValueError("FareSearchCriteria.passengers must cover at least one passenger.")
        if any(count < 0 for count in self.passengers.values()):
            raise ValueError("Passenger counts must be non-negative.")
        if self.return_date is not None and self.return_date < self.outbound_date:
            raise ValueError("return_date must be on or after outbound_date.")
        overlap = set(self.airline_whitelist) & set(self.airline_blacklist)
        if overlap:
            raise ValueError(f"airline_whitelist and airline_blacklist overlap: {sorted(overlap)}.")
        return self


@runtime_checkable
class FareSearchDriver(Driver, Protocol):
    """Shop for fares against a GDS, NDC provider, or consolidator."""

    async def search(self, criteria: FareSearchCriteria) -> list[Fare]:
        """Return candidate fares matching `criteria`.

        Side effects: none (read-only shopping). Safe to call repeatedly;
        results will vary as availability and pricing drift. Fare.valid_until
        on each result signals when the offer must be re-priced.

        Idempotent: yes (no vendor-side state change).

        Raises:
            AuthenticationError, AuthorizationError, RateLimitError,
            TransientError, PermanentError, ValidationFailedError,
            UpstreamTimeoutError.
        """
        ...


__all__ = ["FareSearchCriteria", "FareSearchDriver"]
