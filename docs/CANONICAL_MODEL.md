# Canonical Domain Model — v0

> Spec lives in [`schemas/canonical/`](../schemas/canonical/). Read this doc
> for the *why*; read the code for the exact shapes.

The canonical model is the single vocabulary every layer above the driver
boundary speaks — agents, tools, the HTTP API, all three clients. If a
vendor type shows up above the drivers, the abstraction is broken.

## v0 scope

v0 covers everything the first vertical slice needs end-to-end:

> Flight enquiry → fare → PNR → ticket → invoice → payment → journal → BSP reconciliation

and enough of the other domains to let the hotel and visa drivers start
building without blocking on schema churn.

| Domain | v0 status |
|---|---|
| Primitives (Money, TaxLine, NationalId, Address, Phone, LocalizedText, Period, ISO types) | **Full** |
| Identity (Client, Passenger, Passport) | **Full** |
| Travel — flights (Itinerary, FlightSegment, Fare, PNR, Ticket) | **Full** |
| Travel — hotels (HotelStay, HotelBooking) | **Skeleton** — fields will expand in v1 |
| Travel — visa (VisaFile, VisaChecklistItem) | **Skeleton** |
| Travel — transfers (TransferSegment) | **Skeleton** |
| Travel — umbrella (Booking) | **Full** |
| Finance (Invoice, Payment, Receipt, LedgerAccount, JournalEntry, BSPReport, Reconciliation) | **Full** |
| Lifecycle (Enquiry, Document, AuditEvent) | **Full** |

**Out of v0 (deferred to v1+):**

- **Vouchers** — separate from HotelBooking and Ticket. Will land with the
  hotel driver work.
- **Voucher / BCD-style fare components** (e.g., Miscellaneous Charges
  Orders, EMDs). Not needed for BSP reconciliation v0.
- **Typed `requirements` on Enquiry.** Currently `dict[str, Any]` so drivers
  and agents can evolve without schema churn. v1 will promote
  frequently-used keys into a typed schema per `EnquiryDomain`.
- **Tenant, User, Role** — these live in the auth layer (D9's open auth
  question). Canonical model only references them by `EntityId`.
- **Messages (email/WhatsApp/SMS)** — will land when the messaging driver
  lands.
- **Cancellation rules / fare rules structured fields.** v0 stores them as
  `LocalizedText` free-form.

## Invariants that matter

### Money

- Always `{ amount: Decimal, currency: ISO4217 }`.
- **No floats.** `Money.__init__` rejects floats explicitly. Pass `Decimal`,
  `int`, or `str`.
- Arithmetic helpers (`+`, `-`, `-x`) require matching currencies and raise
  otherwise. Cross-currency math is an FX concern and is deliberately not
  modeled in v0.
- Refunds and credit notes are represented as negative `amount` — the sign
  carries meaning.

### Tax

- Tax is always a `list[TaxLine]` — never a single rate field.
- Each line carries its own `TaxRegime`, regime-local `code` (`CGST` /
  `SGST` / `IGST` / `VAT-standard`…), `rate_bps` (basis points — no float
  rate math), taxable base, and tax amount.
- **There is no `gst_rate` anywhere in shared code.** GST-India is produced
  by the India-GST driver composing `TaxLine`s. VAT drivers do the same for
  VAT. `TaxRegime.NONE` represents zero-rated / out-of-scope lines.
- Sub-national jurisdiction (e.g., Indian state, US state, Canadian
  province) is handled inside regime-specific drivers; the canonical type
  only carries a country-level `jurisdiction` field when the regime needs it.

### Identity

- `Passport` is the universal identity. It's optional on `Passenger` — a
  passenger may enter the system with only a name during `EnquiryStatus.GATHERING`.
- `NationalId` entries are country-keyed and stored as `SecretStr` to keep
  accidental logging exposure down. Aadhaar, PAN, SSN, Emirates ID, NRIC,
  CPF all go through this one type. **They never appear as direct fields.**
- `Client.tax_registrations` holds GSTIN / VAT / TRN / ABN / EIN etc. —
  country-scoped, kind as free-form string; the registry of valid kinds per
  country lives in the tax driver, not the model.

### Addresses

- Always have `country: CountryCode`. `region` and `postal_code` are
  generic, free-form, optional.
- **No `state` field. No `pincode` field.** India's state + PIN validation
  lives in the India address validator, not on the canonical type.

### Time

- All timestamps are UTC. `Period.start` and `Period.end` validators reject
  naive datetimes.
- Date fields (`issue_date`, `expiry_date`, `entry_date`, `check_in`) are
  calendar dates without timezone — they represent "the date printed on the
  document", which is independent of UTC.

### Double entry

- `JournalEntry.lines` has at least 2 entries.
- Every `JournalLine` sets **exactly one** of `debit` / `credit` (the other
  side of the entry is a different line).
- Per-currency totals must balance. Multi-currency journal entries are
  allowed (FX gain/loss, intra-tenant transfers) provided each currency
  balances on its own.

### Audit

- Every side-effect tool call produces an `AuditEvent`. Append-only.
- Approval metadata (`approved_by`, `approved_at`) is captured at the audit
  layer, not on the domain object. This means we can answer "who approved
  this ticket issuance?" without schema pollution on `Ticket`.

## The globalization contract (D8) in action

| Concern | Canonical representation | India-specific logic lives in… |
|---|---|---|
| Currency | `Money.currency: ISO4217` | n/a — INR is just one currency |
| Tax rate | `TaxLine.rate_bps` | India-GST driver composes CGST/SGST/IGST lines |
| GSTIN | `Client.tax_registrations: [{country: 'IN', kind: 'GSTIN', number: ...}]` | India-GST driver validates format |
| Aadhaar / PAN | `Passenger.national_ids: [{country: 'IN', kind: 'aadhaar'|'pan', value: ...}]` | India drivers that require them |
| State / PIN | `Address.region` (free-form) + `Address.postal_code` | India address validator (future) |
| Phone | `Phone.e164` | E.164 is universal; no India format in the model |
| Date / number rendering | Presentation layer only | The UI renders lakhs/crores; the model doesn't |
| Statutory filings | Not in the canonical model at all | India-GST-filing driver, India-TDS-filing driver |

## Evolution policy

1. **Additive changes are cheap.** New optional fields on existing models,
   new enum values, new models — all fine between v0 and v1.
2. **Breaking changes require a version bump and a migration plan.**
   Canonical model versions are tied to git tags. `@voyagent/core` pins a
   specific version; older clients continue to work against older API
   surfaces until upgraded.
3. **The JSON Schema is the contract.** Generated from the FastAPI app's
   OpenAPI endpoint; checked into `packages/core/src/generated.ts`. CI
   verifies the generated file is fresh on every push. See
   [STACK.md — Pydantic → TS contract flow](./STACK.md#the-pydantic--ts-contract-flow).
4. **Vendor-specific fields never earn their way into canonical types.**
   If a driver needs to carry vendor extras, they ride on a `source_ref: str`
   or a driver-private extension store, not on the canonical fields.

## What goes where

A good heuristic for deciding whether a concept belongs in the canonical
model:

- **In the canonical model** if it's meaningful to more than one driver.
  A `Money` value, a `Passenger`, a `TaxLine`, a `Reconciliation` item —
  every driver agrees on what these mean.
- **In a driver** if it's a vendor or country specialization: Amadeus
  queue codes, Tally TDL tags, VFS Schengen form field IDs, GST HSN codes,
  India-PAN format validation.
- **In the tool runtime** if it's about orchestration: side-effect flags,
  approval gates, retry policy.
- **In platform services** if it's about tenancy, auth, or audit plumbing.

## Open schema questions (non-blocking for v0)

- **Tenant / User / Role types** — deferred until we pick an auth provider
  (open question in the README).
- **Currency precision** — Pydantic `Decimal` is arbitrary precision; we may
  want per-currency rounding rules (JPY has 0 decimals, KWD has 3) enforced
  at the runtime layer. Not modeled in v0.
- **FX rates** — a `FxRate` primitive and a `ForexQuote` type will be
  needed when we ship multi-currency invoices in production. Stub for now;
  not used by the first vertical slice.
- **Cancellation rules / fare rules** — currently `LocalizedText`; will
  promote to structured when cancellation automation lands.
- **Hotel `board_type` and `room_type`** — free-form in v0; will enumerate
  in v1 after we see what the first two hotel-bank drivers actually emit.

## How this doc evolves

- Changes to invariants above require a DECISIONS.md entry.
- Adding a new canonical model file gets a pointer in the table above.
- Deprecations list the target removal version and the replacement.
