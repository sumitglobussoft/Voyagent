# Voyagent drivers — index

Voyagent is GDS-agnostic and accounting-software-agnostic. Each vendor
integration lives behind a **driver** — a small adapter that speaks the
vendor's API and exposes the canonical Voyagent surface.

This page is the index. For the "how do I get credentials from vendor
X" side, cross-reference [`VENDOR_ONBOARDING.md`](./VENDOR_ONBOARDING.md).
For the technical interface a driver must implement, see
[`ARCHITECTURE.md`](./ARCHITECTURE.md#drivers).

## Driver catalogue

| Driver              | Category           | Status   | Setup guide                         |
| ------------------- | ------------------ | -------- | ----------------------------------- |
| Amadeus Self-Service | GDS (flights)     | Beta     | [`drivers/AMADEUS.md`](./drivers/AMADEUS.md) |
| TBO Holidays        | Consolidator       | Beta     | [`drivers/TBO.md`](./drivers/TBO.md) |
| Tally Prime         | Accounting (IN)    | Alpha    | [`drivers/TALLY.md`](./drivers/TALLY.md) |
| BSP India           | Settlement (IATA)  | Alpha    | [`drivers/BSP_INDIA.md`](./drivers/BSP_INDIA.md) |
| VFS Global          | Visa processing    | Alpha    | [`drivers/VFS.md`](./drivers/VFS.md) |

**Status legend:**

* **Alpha** — driver exists, exercises the canonical surface end-to-end
  on the sandbox, but needs more production hardening.
* **Beta** — works in production for at least one pilot tenant.
* **GA** — hardened, documented, SLAs published.

## How drivers fit together

```
+---------------+
|  Agent tool   |   (canonical call, e.g. "search flights")
+-------+-------+
        |
        v
+---------------+
|  Driver       |   (translates canonical -> vendor API)
+-------+-------+
        |
        v
+---------------+
|  Vendor API   |   (Amadeus, Tally, VFS, ...)
+---------------+
```

The canonical contract is defined by the Pydantic v2 models under
`schemas/canonical/`. Any driver that implements these signatures can
be dropped in without touching the rest of the stack — that's the
whole point of the abstraction, and it's why Voyagent can swap
Amadeus for Sabre for Galileo (or Tally for Zoho for Busy) without
rewriting the product.

## Adding a new driver

See [`VENDOR_ONBOARDING.md`](./VENDOR_ONBOARDING.md) for the full
vendor-side timeline (credentials, contracts, sandbox access) and
[`ARCHITECTURE.md`](./ARCHITECTURE.md) for the code-side contract.
