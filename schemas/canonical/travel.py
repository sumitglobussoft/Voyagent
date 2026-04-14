"""Travel — v0.

Itineraries, flight & hotel segments, fares, PNRs, tickets, bookings, visa
files. v0 fleshes out the flight side for the first vertical slice; hotel
and visa types are included as usable skeletons so drivers can build against
them, but some fields will expand in v1.

No vendor-specific fields leak into this module. 'source' identifies which
driver produced a record — Amadeus, Sabre, TBO, Hotelbeds, VFS — but the
fields are all canonical.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .primitives import (
    CountryCode,
    CurrencyCode,
    EntityId,
    IATACode,
    LocalizedText,
    Money,
    Period,
    TaxLine,
    Timestamps,
    _strict,
)

# --------------------------------------------------------------------------- #
# Segments                                                                    #
# --------------------------------------------------------------------------- #


class CabinClass(StrEnum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class SegmentStatus(StrEnum):
    PLANNED = "planned"          # in a quotation, not yet held
    HELD = "held"                # airline-held, not ticketed
    CONFIRMED = "confirmed"      # ticketed / vouchered
    FLOWN = "flown"              # post-travel
    CANCELLED = "cancelled"
    SCHEDULE_CHANGE = "schedule_change"


class BaggageAllowance(BaseModel):
    model_config = _strict()

    checked_pieces: int | None = None
    checked_weight_kg: int | None = None
    cabin_pieces: int | None = None
    cabin_weight_kg: int | None = None


class FlightSegment(BaseModel):
    """A single flight leg. Does not carry price — price lives on Fare."""

    model_config = _strict()

    kind: Literal["flight"] = "flight"
    id: EntityId

    marketing_carrier: IATACode = Field(description="Airline whose flight number is used.")
    operating_carrier: IATACode | None = Field(default=None, description="Airline actually operating, if codeshare.")
    flight_number: str = Field(pattern=r"^[0-9]{1,4}[A-Z]?$")

    origin: IATACode = Field(description="IATA airport code of departure.")
    destination: IATACode
    departure_at: datetime = Field(description="Scheduled departure in UTC.")
    arrival_at: datetime = Field(description="Scheduled arrival in UTC.")

    cabin: CabinClass
    booking_class: str | None = Field(default=None, description="RBD letter — regime-local to airlines.")
    fare_basis: str | None = None

    aircraft: str | None = None
    baggage: BaggageAllowance | None = None
    status: SegmentStatus = SegmentStatus.PLANNED

    @field_validator("departure_at", "arrival_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware (UTC).")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _arrival_after_departure(self) -> FlightSegment:
        if self.arrival_at <= self.departure_at:
            raise ValueError("arrival_at must be after departure_at.")
        return self


class HotelStay(BaseModel):
    """A stay at one hotel property. v0 skeleton — fields will expand in v1
    as hotel-bank drivers land (room codes, board types, cancellation rules)."""

    model_config = _strict()

    kind: Literal["hotel_stay"] = "hotel_stay"
    id: EntityId

    property_name: str
    property_ref: str | None = Field(default=None, description="Driver-local hotel identifier.")
    address_country: CountryCode

    check_in: date
    check_out: date
    nights: int = Field(ge=1)

    room_type: str | None = None
    board_type: str | None = Field(default=None, description="Free-form in v0: 'BB', 'HB', 'FB', 'AI'. Will be enumerated in v1.")
    guest_count: int = Field(ge=1)

    status: SegmentStatus = SegmentStatus.PLANNED

    @model_validator(mode="after")
    def _stay_sane(self) -> HotelStay:
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in.")
        expected = (self.check_out - self.check_in).days
        if self.nights != expected:
            raise ValueError(f"nights ({self.nights}) does not match check-in/out range ({expected}).")
        return self


class TransferSegment(BaseModel):
    """A ground transfer. Skeleton in v0; fleshed out when transport drivers land."""

    model_config = _strict()

    kind: Literal["transfer"] = "transfer"
    id: EntityId

    from_location: str
    to_location: str
    pickup_at: datetime
    vehicle_type: str | None = None
    is_private: bool = True
    status: SegmentStatus = SegmentStatus.PLANNED


ItinerarySegment = Annotated[
    FlightSegment | HotelStay | TransferSegment,
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Itinerary                                                                   #
# --------------------------------------------------------------------------- #


class Itinerary(Timestamps):
    """An ordered set of segments for one or more passengers."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId
    enquiry_id: EntityId | None = None
    passenger_ids: list[EntityId] = Field(min_length=1)
    segments: list[ItinerarySegment] = Field(min_length=1)

    notes: LocalizedText | None = None


# --------------------------------------------------------------------------- #
# Fare                                                                        #
# --------------------------------------------------------------------------- #


class FareComponent(BaseModel):
    """An additive component of a fare: base, YQ/fuel, agency markup, discount.

    Taxes are modeled separately as TaxLine so tax reporting pivots cleanly.
    """

    model_config = _strict()

    label: str
    amount: Money


class Fare(BaseModel):
    """A priced offer for a passenger against an itinerary.

    A quotation for N passengers + M segments produces multiple Fare records
    (one per passenger type, possibly per source). The agent layer compares
    across Fares to pick one to book.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId
    itinerary_id: EntityId
    passenger_id: EntityId

    base: Money
    fees: list[FareComponent] = Field(default_factory=list)
    taxes: list[TaxLine] = Field(default_factory=list)
    total: Money

    fare_rules: LocalizedText | None = None
    source: str = Field(description="Driver identifier: 'amadeus', 'sabre', 'tbo', 'airline_direct', ...")
    source_ref: str | None = Field(default=None, description="Vendor-local offer/fare reference.")
    valid_until: datetime | None = Field(
        default=None,
        description="Time-to-live from the source. Quotes past this instant must be re-priced.",
    )

    @model_validator(mode="after")
    def _currency_consistency(self) -> Fare:
        currencies = {self.base.currency, self.total.currency}
        currencies.update(f.amount.currency for f in self.fees)
        currencies.update(t.tax_amount.currency for t in self.taxes)
        if len(currencies) > 1:
            raise ValueError(f"Fare components must share a currency (found {currencies}).")
        return self


# --------------------------------------------------------------------------- #
# PNR & Ticket                                                                #
# --------------------------------------------------------------------------- #


class PNRStatus(StrEnum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    TICKETED = "ticketed"
    CANCELLED = "cancelled"
    SCHEDULE_CHANGE = "schedule_change"


class PNR(Timestamps):
    """A reservation record with a GDS or airline. The `locator` is the
    record locator the vendor uses; `source` tells which system owns it.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    locator: str = Field(description="Record locator, typically 6 characters.")
    source: str = Field(description="Driver identifier: 'amadeus', 'sabre', 'galileo', 'airline_direct', ...")
    source_ref: str | None = None

    status: PNRStatus
    passenger_ids: list[EntityId] = Field(min_length=1)
    segment_ids: list[EntityId] = Field(min_length=1)
    fare_ids: list[EntityId] = Field(default_factory=list)

    ticket_time_limit: datetime | None = None


class TicketStatus(StrEnum):
    OPEN = "open"
    FLOWN = "flown"
    REFUNDED = "refunded"
    EXCHANGED = "exchanged"
    VOID = "void"


class Ticket(Timestamps):
    """An issued e-ticket. A PNR may have many Tickets (one per passenger,
    and more across reissues)."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    number: str = Field(pattern=r"^[0-9]{3}-?[0-9]{10}$", description="13-digit e-ticket number, with optional hyphen after the airline prefix.")
    pnr_id: EntityId
    passenger_id: EntityId
    issued_at: datetime
    issuing_airline: IATACode
    issuing_agent_iata: str | None = Field(default=None, description="IATA agency code that issued the ticket.")

    base_amount: Money
    tax_amount: Money
    total_amount: Money

    status: TicketStatus = TicketStatus.OPEN


# --------------------------------------------------------------------------- #
# HotelBooking                                                                #
# --------------------------------------------------------------------------- #


class HotelBookingStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class HotelBooking(Timestamps):
    """A confirmation of a hotel stay with a supplier. Counterpart to PNR
    on the hotel side. Skeleton in v0."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    stay_id: EntityId
    supplier: str = Field(description="Driver identifier: 'hotelbeds', 'tbo_hotels', 'direct_<property>', ...")
    supplier_ref: str = Field(description="Supplier's confirmation number.")
    status: HotelBookingStatus

    cost: Money
    currency: CurrencyCode


# --------------------------------------------------------------------------- #
# Visa                                                                        #
# --------------------------------------------------------------------------- #


class VisaStatus(StrEnum):
    DRAFT = "draft"
    CHECKLIST_PREPARED = "checklist_prepared"
    DOCS_COLLECTING = "docs_collecting"
    DOCS_VERIFIED = "docs_verified"
    APPLICATION_SUBMITTED = "application_submitted"
    APPOINTMENT_BOOKED = "appointment_booked"
    BIOMETRICS_DONE = "biometrics_done"
    IN_PROCESS = "in_process"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class VisaChecklistItem(BaseModel):
    model_config = _strict()

    label: LocalizedText
    required: bool = True
    collected: bool = False
    document_id: EntityId | None = None
    notes: LocalizedText | None = None


class VisaFile(Timestamps):
    """A visa application for one passenger to one destination."""

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    passenger_id: EntityId
    destination_country: CountryCode
    visa_category: str = Field(description="Category name local to destination country ('tourist', 'business', 'transit', 'umrah', ...).")

    status: VisaStatus = VisaStatus.DRAFT
    checklist: list[VisaChecklistItem] = Field(default_factory=list)

    source: str = Field(description="Driver identifier: 'vfs_in_schengen', 'bls_in_uk', 'embassy_direct', ...")
    application_ref: str | None = None
    appointment_at: datetime | None = None
    outcome_date: date | None = None


# --------------------------------------------------------------------------- #
# Booking (umbrella)                                                          #
# --------------------------------------------------------------------------- #


class BookingStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_CANCELLED = "partially_cancelled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Booking(Timestamps):
    """The top-level record that aggregates a single client sale.

    A Booking can span PNRs, HotelBookings, VisaFiles, and Vouchers produced
    across multiple drivers. Invoices reference Booking, not the underlying
    vendor records.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId
    client_id: EntityId
    enquiry_id: EntityId | None = None

    pnr_ids: list[EntityId] = Field(default_factory=list)
    hotel_booking_ids: list[EntityId] = Field(default_factory=list)
    visa_file_ids: list[EntityId] = Field(default_factory=list)

    status: BookingStatus
    total: Money
    travel_period: Period | None = None


__all__ = [
    "BaggageAllowance",
    "Booking",
    "BookingStatus",
    "CabinClass",
    "Fare",
    "FareComponent",
    "FlightSegment",
    "HotelBooking",
    "HotelBookingStatus",
    "HotelStay",
    "Itinerary",
    "ItinerarySegment",
    "PNR",
    "PNRStatus",
    "SegmentStatus",
    "Ticket",
    "TicketStatus",
    "TransferSegment",
    "VisaChecklistItem",
    "VisaFile",
    "VisaStatus",
]
