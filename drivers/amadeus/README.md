# drivers/amadeus

Reference implementation of a Voyagent driver against **Amadeus
Self-Service** REST APIs (`https://test.api.amadeus.com`). This is the
first concrete driver in the tree, and the one Sabre / TBO / airline-direct
drivers should mirror in shape.

## What this driver implements

| Capability       | Support         | Notes                                               |
| ---------------- | --------------- | --------------------------------------------------- |
| `search`         | `full`          | `GET /v2/shopping/flight-offers`.                   |
| `create`         | `full` *manifest* / raises in v0 | See "Known v0 limitation" below. |
| `read`           | `full`          | `GET /v1/booking/flight-orders/{id}`.               |
| `cancel`         | `full`          | `DELETE /v1/booking/flight-orders/{id}`.            |
| `queue_read`     | `not_supported` | Self-Service has no GDS queue concept.              |
| `issue_ticket`   | `not_supported` | Self-Service is booking-only.                       |
| `void_ticket`    | `not_supported` | Self-Service is booking-only.                       |

Ticket issuance and voiding live on **Amadeus Enterprise / Selling Platform**,
not on Self-Service. A future `drivers/amadeus_enterprise` will declare those
`full`. Until then, route ticketing through a BSP-layer driver.

## Configuration

All settings are loaded from `VOYAGENT_AMADEUS_*` environment variables via
`pydantic-settings`:

| Env var                            | Default                          |
| ---------------------------------- | -------------------------------- |
| `VOYAGENT_AMADEUS_API_BASE`        | `https://test.api.amadeus.com`   |
| `VOYAGENT_AMADEUS_CLIENT_ID`       | *(empty — required for live)*    |
| `VOYAGENT_AMADEUS_CLIENT_SECRET`   | *(empty — required for live)*    |
| `VOYAGENT_AMADEUS_TIMEOUT_SECONDS` | `30`                             |
| `VOYAGENT_AMADEUS_MAX_RETRIES`     | `2`                              |

Get sandbox credentials at <https://developers.amadeus.com> — create an
app under "Self-Service APIs" and use the test-environment keys.

## Driver-specific gotchas

- **Prices are strings.** Amadeus returns `price.total = "123.45"` as a
  JSON string. We parse with `Decimal(str(value))` — **never** `float`.
- **Datetimes are local-to-origin with no offset.** `segment.departure.at`
  is `"2024-08-12T14:30:00"` (local to the departure airport), not UTC.
  Canonical `FlightSegment` requires timezone-aware UTC; the mapper
  currently attaches UTC as a v0 compromise. See the `_parse_datetime`
  TODO — production needs airport-timezone resolution.
- **Offer TTLs are tight.** `lastTicketingDateTime` can be as little as
  minutes after search. Fares are written through to canonical
  `Fare.valid_until`; the agent layer must re-price past that.
- **Tax regime is opaque.** Self-Service lists taxes by code (`YQ`, `YR`,
  `GB`, ...) but does not classify them. Every `TaxLine` currently uses
  `TaxRegime.NONE`; a jurisdiction-aware driver can re-classify.
- **Cabin lives on the traveler, not the segment.** The mapper emits
  `CabinClass.ECONOMY` by default on segments — callers that need
  traveler-specific cabin must read it from `fareDetailsBySegment[]`.
- **Record locator ≠ order id.** Amadeus keys orders by its own id;
  `read(locator)` actually takes the order id. Humans see the 6-char
  airline record locator under `associatedRecords[].reference`.

## Known v0 limitation: `create`

Amadeus requires the **full original flight-offer JSON** — re-priced via
`POST /v1/shopping/flight-offers/pricing` — to be sent as the body of
`POST /v1/booking/flight-orders`, along with traveler details. The
`PNRDriver.create` signature only receives canonical `fare_ids` and
`passenger_ids`; to honour the Protocol we need an **offer cache** the
agent runtime is still designing.

Until then, `create` raises `PermanentError`. When the cache lands, the
driver will look up the cached Amadeus offer, hydrate travelers from
`Passenger`, POST, and map the response through
`amadeus_order_to_pnr`.

## How to extend this driver or write a sibling

1. **Start with `mapping.py`.** Pure, typed vendor-JSON → canonical
   functions are the heart. They have no I/O and are independently
   testable. Every other module exists to feed them clean input.
2. **`errors.py` before `client.py`.** A driver's value comes from
   raising the *right* `DriverError` subclass. Map first, then retry.
3. **Use `httpx.AsyncClient`** and a single `AmadeusClient`-style
   wrapper. Retries, backoff and auth injection live there — not in
   each method.
4. **Honour the Protocol signature.** When vendor constraints demand
   extra context (like Amadeus offer bodies), document the runtime-side
   workaround — don't add vendor-specific parameters to Protocol methods.
5. **Manifest `capabilities` honestly.** `"not_supported"` is better than
   a silent stub. The orchestrator routes around unsupported capabilities.

## Layout

```
drivers/amadeus/
  __init__.py       — re-exports AmadeusDriver, AmadeusConfig
  config.py         — pydantic-settings config
  auth.py           — OAuth2 client-credentials TokenManager
  errors.py         — map_amadeus_error(response) -> DriverError
  client.py         — AmadeusClient: httpx + retries + auth
  mapping.py        — pure vendor-JSON → canonical functions
  driver.py         — AmadeusDriver class
```
