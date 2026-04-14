"""Canonical primitives — v0.

Globalization-safe building blocks. Every higher-level model in this package
is composed from these types. See docs/CANONICAL_MODEL.md and
docs/DECISIONS.md#d8 for the rules these primitives encode.

Invariants:
- All monetary values carry an ISO-4217 currency code. No bare numbers for money.
- All monetary arithmetic uses Decimal. Never float.
- All country references are ISO-3166-1 alpha-2. No free-form country strings.
- All phone numbers are stored as E.164. Local formats are a rendering concern.
- All timestamps are UTC. Locale rendering happens at the presentation layer.
- No India-specific fields (GST, PIN code, Aadhaar, PAN) in shared types.
  Country-specific concepts live behind country-scoped drivers and per-tenant
  configuration. See D8.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

# --------------------------------------------------------------------------- #
# ISO code aliases — string newtypes with pattern validation                  #
# --------------------------------------------------------------------------- #

CountryCode = Annotated[
    str,
    StringConstraints(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$"),
    Field(description="ISO 3166-1 alpha-2 country code, uppercase (e.g. 'IN', 'AE', 'GB')."),
]

CurrencyCode = Annotated[
    str,
    StringConstraints(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"),
    Field(description="ISO 4217 currency code, uppercase (e.g. 'INR', 'USD', 'AED')."),
]

LanguageCode = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z][a-zA-Z]{1,3})?$"),
    Field(description="BCP 47 language tag, lowercased language + optional region (e.g. 'en', 'en-IN', 'hi', 'ar-AE')."),
]

IATACode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z0-9]{2,3}$"),
    Field(description="IATA location or airline code. 3 letters for airports, 2 for airlines."),
]

E164Phone = Annotated[
    str,
    StringConstraints(pattern=r"^\+[1-9]\d{6,14}$"),
    Field(description="Phone number in E.164 format, including leading '+' and country code."),
]

EmailStr = Annotated[
    str,
    StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    Field(description="Email address. Light-touch validation at the model layer; transport validates more strictly."),
]

# Entity IDs are UUIDv7-shaped strings. We store as str so they serialize
# cleanly to JSON without UUID object friction across the FastAPI boundary.
# A helper in the runtime generates UUIDv7; this spec only enforces shape.
EntityId = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
    Field(description="Opaque entity identifier (UUIDv7, lowercase, hyphenated)."),
]


def _strict() -> ConfigDict:
    """Shared Pydantic config for canonical models."""
    return ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        ser_json_timedelta="iso8601",
        ser_json_bytes="base64",
    )


# --------------------------------------------------------------------------- #
# Common enums                                                                #
# --------------------------------------------------------------------------- #


class Gender(StrEnum):
    """Gender as required by airlines and visa authorities. Separate from
    self-identified gender at the social layer, which is a presentation concern."""

    MALE = "M"
    FEMALE = "F"
    UNSPECIFIED = "X"


# --------------------------------------------------------------------------- #
# Money                                                                       #
# --------------------------------------------------------------------------- #


class Money(BaseModel):
    """A monetary amount in a specific currency.

    Uses Decimal for exact arithmetic — never float. The currency is always
    explicit; there is no implicit tenant or locale default.

    Arithmetic helpers are intentionally minimal in v0. Cross-currency math is
    an FX concern and is not modeled here.
    """

    model_config = _strict()

    amount: Decimal = Field(description="Decimal amount. Sign carries meaning (refunds are negative).")
    currency: CurrencyCode

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, str)):
            return Decimal(v)
        if isinstance(v, float):
            raise ValueError("Money.amount must not be float — pass str, int, or Decimal.")
        raise ValueError(f"Cannot coerce {type(v).__name__} to Decimal amount.")

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot combine Money in different currencies ({self.currency} vs {other.currency})."
            )

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)


# --------------------------------------------------------------------------- #
# Tax                                                                         #
# --------------------------------------------------------------------------- #


class TaxRegime(StrEnum):
    """Tax regimes. GST-India is one implementation — not the model.

    Add a new regime by appending a value here and shipping a tax driver under
    drivers/<regime>/. Shared code must not branch on a specific regime.
    """

    GST_INDIA = "gst_india"
    VAT_UK = "vat_uk"
    VAT_EU = "vat_eu"
    VAT_UAE = "vat_uae"
    GST_SINGAPORE = "gst_sg"
    SST_MALAYSIA = "sst_my"
    SALES_TAX_US = "sales_tax_us"
    NONE = "none"  # For zero-rated or out-of-scope items.


class TaxLine(BaseModel):
    """One tax component applied to a taxable base.

    For a single Indian GST line item this may expand to up to three lines
    (CGST, SGST, IGST) — that composition is an India-driver concern; this
    type only says "a tax was applied of kind X at rate Y."
    """

    model_config = _strict()

    regime: TaxRegime
    code: str = Field(description="Regime-local code: e.g. 'CGST', 'SGST', 'IGST', 'VAT-standard', 'VAT-reduced'.")
    rate_bps: int = Field(
        ge=0,
        le=100_000,
        description="Tax rate in basis points (1% = 100 bps). Avoids float rate math.",
    )
    taxable_amount: Money
    tax_amount: Money
    jurisdiction: CountryCode | None = Field(
        default=None,
        description="Country where the tax is levied. Sub-national jurisdictions are regime-specific.",
    )

    @model_validator(mode="after")
    def _currency_consistency(self) -> TaxLine:
        if self.taxable_amount.currency != self.tax_amount.currency:
            raise ValueError("taxable_amount and tax_amount must share a currency.")
        return self


# --------------------------------------------------------------------------- #
# Identity documents                                                          #
# --------------------------------------------------------------------------- #


class NationalIdKind(StrEnum):
    """National identity document kinds. Extend as new markets come online.

    These are stored only when an integration requires them (e.g. Indian domestic
    fare bookings may require PAN for high-value transactions). They never
    appear as required fields on Passenger or Client.
    """

    AADHAAR = "aadhaar"           # IN
    PAN = "pan"                   # IN
    EMIRATES_ID = "emirates_id"   # AE
    NRIC = "nric"                 # SG
    SSN = "ssn"                   # US
    NIN = "nin"                   # UK / NG
    CPF = "cpf"                   # BR
    OTHER = "other"


class NationalId(BaseModel):
    """A country-scoped national identity document.

    Values are held in SecretStr to reduce accidental logging exposure.
    The presentation layer chooses whether and how to render the raw value.
    """

    model_config = _strict()

    country: CountryCode
    kind: NationalIdKind
    value: SecretStr
    issued_on: date | None = None
    expires_on: date | None = None


# --------------------------------------------------------------------------- #
# Address                                                                     #
# --------------------------------------------------------------------------- #


class Address(BaseModel):
    """A postal address. Country is required and drives per-country validation
    in the country-scoped validators (not in this model).

    Deliberately has no 'state' / 'pincode' fields — region/postal code are
    generic so we can address a London flat or a Dubai tower without modeling
    India specifically.
    """

    model_config = _strict()

    country: CountryCode
    line1: str
    line2: str | None = None
    city: str
    region: str | None = Field(default=None, description="State / province / emirate / prefecture, free-form.")
    postal_code: str | None = Field(default=None, description="Postal / ZIP / PIN code, free-form.")
    attention: str | None = Field(default=None, description="Optional 'attention to' line for business mail.")


# --------------------------------------------------------------------------- #
# Contact handles                                                             #
# --------------------------------------------------------------------------- #


class Phone(BaseModel):
    model_config = _strict()

    e164: E164Phone
    label: str | None = Field(default=None, description="Free-form label: 'mobile', 'office', 'whatsapp'.")


class Email(BaseModel):
    model_config = _strict()

    address: EmailStr
    label: str | None = None


# --------------------------------------------------------------------------- #
# Localized text                                                              #
# --------------------------------------------------------------------------- #


class LocalizedText(BaseModel):
    """Text that may be translated. v1 is English-only in the UI, but every
    user-facing string is born ready for i18n so we never have to do a
    painful sweep later."""

    model_config = _strict()

    default: str = Field(description="Canonical text in the default tenant language.")
    translations: dict[LanguageCode, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Temporal range                                                              #
# --------------------------------------------------------------------------- #


class Period(BaseModel):
    """A half-open UTC time range [start, end)."""

    model_config = _strict()

    start: datetime
    end: datetime | None = None

    @field_validator("start", "end")
    @classmethod
    def _require_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("Period datetimes must be timezone-aware (UTC).")
        if v.utcoffset() != timezone.utc.utcoffset(v):
            # Allow any explicit tz; normalize to UTC for storage.
            return v.astimezone(timezone.utc)
        return v

    @model_validator(mode="after")
    def _ordered(self) -> Period:
        if self.end is not None and self.end <= self.start:
            raise ValueError("Period end must be strictly after start.")
        return self


# --------------------------------------------------------------------------- #
# Mixins                                                                      #
# --------------------------------------------------------------------------- #


class Timestamps(BaseModel):
    """Mixin for created/updated tracking. Composition, not inheritance."""

    model_config = _strict()

    created_at: datetime
    updated_at: datetime


__all__ = [
    "Address",
    "CountryCode",
    "CurrencyCode",
    "E164Phone",
    "Email",
    "EmailStr",
    "EntityId",
    "Gender",
    "IATACode",
    "LanguageCode",
    "LocalizedText",
    "Money",
    "NationalId",
    "NationalIdKind",
    "Period",
    "Phone",
    "TaxLine",
    "TaxRegime",
    "Timestamps",
]
