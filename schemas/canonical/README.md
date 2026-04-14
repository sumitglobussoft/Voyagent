# schemas/canonical

The **canonical domain model** — Pydantic v2 definitions that every agent,
tool, and driver in Voyagent speaks. The single source of truth.

## Status

**v0 — planning-phase draft.** These files are not yet wired into a running
Python workspace (`pyproject.toml` is not scaffolded yet). They are the spec
the first vertical slice will build against.

## Design rationale

See [docs/CANONICAL_MODEL.md](../../docs/CANONICAL_MODEL.md) for the full
design doc — invariants, globalization contract, evolution policy, and what
is intentionally deferred to v1.

## Layout

| File | Scope |
|---|---|
| `primitives.py` | `Money`, `TaxLine`, `NationalId`, `Address`, `Phone`, `Email`, `LocalizedText`, `Period`, ISO-code aliases (`CountryCode`, `CurrencyCode`, `LanguageCode`, `IATACode`), `Gender`, `EntityId`, `Timestamps` |
| `identity.py` | `Client`, `Passenger`, `Passport`, `TaxRegistration` |
| `travel.py` | `Itinerary`, `FlightSegment`, `HotelStay`, `TransferSegment`, `Fare`, `PNR`, `Ticket`, `HotelBooking`, `VisaFile`, `Booking` |
| `finance.py` | `Invoice`, `Payment`, `Receipt`, `LedgerAccount`, `JournalEntry`, `BSPReport`, `Reconciliation` |
| `lifecycle.py` | `Enquiry`, `Document`, `AuditEvent` |
| `__init__.py` | Central exports. Everything is importable as `from voyagent.schemas.canonical import Money, Passenger, ...`. |

## The rules that matter

1. **Vendors never leak upward.** `source: str` names a driver; no
   vendor-specific fields sit on canonical models.
2. **Money is always `{ amount: Decimal, currency: ISO4217 }`.** No floats.
   No bare numbers.
3. **Tax is modeled as `TaxLine[]` with a `TaxRegime` tag.** GST-India is one
   regime. VAT, SST, sales tax are peers — not special cases.
4. **Country-specific IDs (Aadhaar, PAN, SSN, Emirates ID) are `NationalId`
   entries**, country-keyed, never direct fields on `Passenger` or `Client`.
5. **Addresses have no 'state' or 'pincode' fields.** `region` and
   `postal_code` are generic; country validators live in drivers.
6. **All timestamps are UTC.** Rendering locality happens at the
   presentation layer.
7. **Double-entry invariants** (debits = credits per currency) are enforced
   in `JournalEntry`.
8. **Every side-effect tool call writes an `AuditEvent`.** Append-only.

CI gate (to be wired when services land): reject merges that introduce
`inr`, `gst`, `aadhaar`, `pan`, or `pincode` tokens in any file outside
country-scoped driver modules.
