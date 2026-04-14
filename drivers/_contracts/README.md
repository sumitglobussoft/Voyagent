# drivers/_contracts

The **adapter-layer contract** for Voyagent. Every integration with an
external system — GDS, hotel bank, visa portal, accounting package,
payment rail, bank, card issuer, messaging provider, tax authority —
implements one or more Protocols from this package and publishes a
`CapabilityManifest`.

Shared code above the driver boundary imports **only** canonical types
(from `schemas.canonical`) and these Protocols. Concrete driver packages
are never imported by agents or tools.

## How to implement a driver

1. Create a package under `drivers/<vendor>/` (e.g. `drivers/amadeus/`).
2. Implement one or more capability Protocols. Protocols are *structural*
   — you do **not** inherit. Just match the method signatures and expose
   `name: str`, `version: str`, and `manifest() -> CapabilityManifest`.
3. Translate vendor types into canonical types at the method boundary.
   No vendor type ever leaks out of the driver.
4. Raise exclusively from `drivers._contracts.errors` — never vendor
   exceptions.
5. Publish a `CapabilityManifest` from `manifest()`. The orchestrator
   reads it at registration time.
6. Register the driver in the tenant's driver registry (covered by
   `services/api` once that lands).

```python
from drivers._contracts import (
    CapabilityManifest, FareSearchDriver, FareSearchCriteria,
)
from schemas.canonical import Fare

class AmadeusFareSearch:
    name = "amadeus"
    version = "1.0.0"

    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            driver="amadeus",
            version=self.version,
            implements=["FareSearchDriver"],
            capabilities={"fare.shop": "full"},
            transport=["soap"],
            requires=["tenant_credentials"],
            tenant_config_schema={...},
        )

    async def search(self, criteria: FareSearchCriteria) -> list[Fare]:
        ...

assert isinstance(AmadeusFareSearch(), FareSearchDriver)  # runtime_checkable
```

## Why every method is async

Drivers do I/O: HTTP, SOAP, SFTP, browser automation, desktop IPC, DB
queries. The agent runtime and the Temporal workers are asyncio-first,
so the contract is uniformly `async def`. A driver that calls a blocking
library internally wraps with `asyncio.to_thread` or `loop.run_in_executor`.

## Canonical types vs driver-layer types

The canonical model (`schemas.canonical`) is the **persistence** contract.
It models things that survive: `PNR`, `Ticket`, `HotelBooking`, `Payment`,
`Invoice`, `Fare`. Anything persisted as a Voyagent record is canonical.

Some things are only passed *through* a driver call and never stored as-is:

- `FareSearchCriteria`, `HotelSearchCriteria` — inputs to shopping calls.
- `HotelOffer` — a pre-booking offer the agent picks from. On confirmation,
  `HotelBookingDriver.book` converts the selected offer into canonical
  `HotelStay` + `HotelBooking`.
- `BankTransaction`, `CardTransaction`, `CardUtilization` — normalized
  statement lines used by reconciliation; matched lines spawn canonical
  `Payment` / `Receipt` records, unmatched ones stay as ephemeral driver
  output.

Driver-layer types live here because they are part of the driver contract
but do not earn a place in the canonical model. They follow the same
strict Pydantic-v2 config (`extra="forbid"`, `str_strip_whitespace=True`,
`validate_assignment=True`) so the boundary stays disciplined.

## Error handling

All drivers raise from `drivers._contracts.errors`:

- `TransientError`, `RateLimitError`, `UpstreamTimeoutError` — retryable.
- `PermanentError`, `ValidationFailedError`, `ConflictError`,
  `NotFoundError`, `AuthenticationError`, `AuthorizationError` — do not
  retry without a fix.
- `CapabilityNotSupportedError` — manifest says this driver cannot do
  what was asked. Orchestrator routes to a fallback driver or degrades.

Each method's docstring lists the errors it may raise and flags whether
it is idempotent. Non-idempotent side-effecting methods expect the
runtime to pass a client-side request key via the driver's documented
channel (metadata dict, vendor-specific header, etc.).
