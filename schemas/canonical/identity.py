"""Identity — v0.

Client, Passenger, Passport. These are the people Voyagent moves through the
world. Aadhaar / PAN / Emirates ID / SSN are optional NationalId entries —
never direct fields — per the globalization contract (see D8).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, SecretStr, model_validator

from .primitives import (
    Address,
    CountryCode,
    Email,
    EntityId,
    Gender,
    LocalizedText,
    NationalId,
    Phone,
    Timestamps,
    _strict,
)


class PassengerType(StrEnum):
    """Airline / visa categorisation. Driven by age cutoffs that differ per
    carrier; the canonical value is what the booking was made under."""

    ADULT = "adult"
    CHILD = "child"
    INFANT = "infant"
    SENIOR = "senior"


class Passport(BaseModel):
    """Travel document. The universal identity in the canonical model.

    Name fields mirror the passport's MRZ exactly — they may differ from a
    passenger's preferred or social name, which belongs on Passenger.
    """

    model_config = _strict()

    number: SecretStr
    issuing_country: CountryCode
    given_name: str = Field(description="Given name as printed on the passport.")
    family_name: str = Field(description="Family / surname as printed on the passport.")
    date_of_birth: date
    gender: Gender
    issue_date: date
    expiry_date: date
    place_of_birth: str | None = None

    @model_validator(mode="after")
    def _dates_sane(self) -> Passport:
        if self.expiry_date <= self.issue_date:
            raise ValueError("Passport expiry_date must be after issue_date.")
        if self.date_of_birth >= self.issue_date:
            raise ValueError("Passport issue_date must be after date_of_birth.")
        return self


class Passenger(Timestamps):
    """A traveler on a booking.

    A passenger is not necessarily a system user — they may be a family member
    of a corporate client, a child, or a guest. Users are modeled separately
    (see auth).
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    type: PassengerType
    given_name: str = Field(description="Preferred given name for communication.")
    family_name: str
    middle_name: str | None = None
    preferred_name: str | None = None

    date_of_birth: date | None = Field(
        default=None,
        description="Required for most airline pricing and all visa work; optional at model level so partial enquiries can exist before collection.",
    )
    gender: Gender | None = None
    nationality: CountryCode | None = None

    passport: Passport | None = None
    national_ids: list[NationalId] = Field(default_factory=list)

    phones: list[Phone] = Field(default_factory=list)
    emails: list[Email] = Field(default_factory=list)
    address: Address | None = None

    notes: LocalizedText | None = None


class ClientKind(StrEnum):
    INDIVIDUAL = "individual"
    CORPORATE = "corporate"
    AGENT = "agent"  # downstream travel agent acting as a client


class Client(Timestamps):
    """The counterparty the travel agency sells to.

    A Client owns a billing relationship (invoices, statements, credit limit).
    Passengers on a booking may or may not include the Client themselves —
    corporates book for their employees, parents book for children.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId

    kind: ClientKind
    display_name: str
    legal_name: str | None = Field(default=None, description="Registered legal name for invoicing.")
    tax_registrations: list[TaxRegistration] = Field(
        default_factory=list,
        description="Country-scoped tax registration identifiers (VAT no., GSTIN, ABN, EIN, etc.).",
    )

    primary_contact_name: str | None = None
    phones: list[Phone] = Field(default_factory=list)
    emails: list[Email] = Field(default_factory=list)
    billing_address: Address | None = None
    shipping_address: Address | None = None

    default_currency: str | None = Field(
        default=None,
        description="ISO 4217 — quotations and invoices default to this currency when unset per-transaction.",
    )
    credit_limit_amount: str | None = None
    credit_limit_currency: str | None = None

    notes: LocalizedText | None = None


class TaxRegistration(BaseModel):
    """A client's tax registration in some country.

    'kind' is free-form because the landscape is messy: GSTIN, VAT, TRN, ABN,
    EIN, NIF... A registry of valid kinds per country lives in the tax
    driver, not here.
    """

    model_config = _strict()

    country: CountryCode
    kind: str = Field(description="Regime-local label: 'GSTIN', 'VAT', 'TRN', 'ABN', 'EIN', ...")
    number: str
    verified: bool = False


__all__ = [
    "Client",
    "ClientKind",
    "Passenger",
    "PassengerType",
    "Passport",
    "TaxRegistration",
]
