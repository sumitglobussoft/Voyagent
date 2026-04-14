# Voyagent tests

Pytest unit tests for the canonical domain model. These tests pin the
invariants documented in [`docs/CANONICAL_MODEL.md`](../docs/CANONICAL_MODEL.md)
and [`docs/DECISIONS.md`](../docs/DECISIONS.md) (D8, D10). They are pure —
no network, no I/O, no database.

## Running

Once the Python workspace is scaffolded (a separate agent is wiring
`pyproject.toml` and making `schemas.canonical` importable):

```
pytest tests/
```

To run a single module:

```
pytest tests/canonical/test_finance.py
```

## Layout

```
tests/
├── __init__.py
├── conftest.py               # shared fixtures: make_entity_id, make_money, utc_now, utc
├── README.md                 # this file
└── canonical/
    ├── __init__.py
    ├── test_primitives.py    # Money, TaxLine, Period, Address, Phone, EntityId
    ├── test_identity.py      # Passport, Passenger (gathering-phase), NationalId
    ├── test_travel.py        # FlightSegment, HotelStay, Fare
    ├── test_finance.py       # InvoiceLine, Invoice, JournalLine, JournalEntry, Reconciliation
    └── test_lifecycle.py     # Enquiry, Document, AuditEvent
```

## Invariants covered

- **Money**: rejects `float`; coerces `str`/`int`/`Decimal`; `+`/`-` require
  matching currencies; negation preserves currency.
- **TaxLine**: `taxable_amount` and `tax_amount` share a currency;
  `rate_bps` bounded 0–100_000.
- **Period**: rejects naive datetimes; `end > start`; normalizes non-UTC
  aware datetimes to UTC.
- **Address / Phone / ISO codes / EntityId**: pattern validation (valid +
  invalid cases), and confirmation that `Address` has no `state`/`pincode`.
- **Passport**: `expiry_date > issue_date > date_of_birth`.
- **Passenger**: minimal gathering-phase construction (only name + type).
- **NationalId**: `value` stored as `SecretStr` and masked in `repr`.
- **FlightSegment**: `arrival_at > departure_at`; rejects naive datetimes;
  `flight_number` regex.
- **HotelStay**: `check_out > check_in`; `nights` matches the range.
- **Fare**: currency consistency across base / fees / taxes / total.
- **Invoice / InvoiceLine**: per-line and invoice-wide currency consistency.
- **JournalLine**: exactly one of `debit` / `credit` is set.
- **JournalEntry**: balanced per currency; multi-currency entries balance
  each currency independently; useful error message on imbalance.
- **Reconciliation**: basic construction.
- **Enquiry**: loose `requirements: dict[str, Any]` accepted as-is.
- **Document**: `sha256` must be 64 lowercase hex chars.
- **AuditEvent**: default `status` is `STARTED`.
