# Tally Prime driver

Tally Prime is the dominant small-business accounting package in India.
The Voyagent Tally driver posts journal entries, sales vouchers, and
receipt vouchers via Tally's XML ODBC server so the agency's books
stay in sync with what happens inside Voyagent — without forcing the
accountant off Tally.

Cross-reference:
* Full onboarding timeline → [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md)
* Driver index → [`../DRIVERS.md`](../DRIVERS.md)

## Local setup

Unlike cloud drivers, Tally runs on the accountant's Windows desktop.
The Voyagent API talks to it over HTTP, so either the API needs a
network path to that desktop or the desktop runs a small Voyagent
relay agent.

1. Enable the **ODBC / HTTP** server inside Tally:
   `F11` → **Features** → **Advanced configuration** → check
   **"Enable ODBC Server"** and note the port (default `9000`).
2. Set environment variables on `services/api` (or on the relay, if
   the Tally box is behind NAT):

   ```bash
   export VOYAGENT_TALLY_URL=http://tally-host:9000
   export VOYAGENT_TALLY_COMPANY="Acme Travel Pvt Ltd"
   ```

3. Restart the API (or relay).
4. Smoke-test by asking the agent:

   > Post a ₹1,000 test journal entry to Tally under "Test Ledger".

## What works today

* **Sales vouchers** for issued tickets (canonical `TicketSale` event).
* **Receipt vouchers** for customer payments.
* **Journal entries** for FX revaluation and round-off.

## What doesn't work yet

* **Ledger master creation** — for now, ledgers must exist in Tally
  before Voyagent posts to them.
* **Multi-GSTIN agencies** — v0 assumes one GSTIN per tenant.
* **Bi-directional sync** — Voyagent → Tally only. Changes made
  directly in Tally are not pulled back.

## Troubleshooting

| Symptom                                  | Likely cause                                | Fix                                                 |
| ---------------------------------------- | ------------------------------------------- | --------------------------------------------------- |
| `Connection refused` on port 9000        | Tally's ODBC server is off                  | F11 → Features → enable ODBC                        |
| `LEDGER NOT FOUND`                       | Ledger name mismatch or extra whitespace    | Paste the exact name from Tally's ledger list       |
| Entries post but with wrong GST          | Tally's GST master is misconfigured         | Fix inside Tally — driver forwards what it's told   |
| Entries missing on the Tally side        | `VOYAGENT_TALLY_COMPANY` wrong              | Must match the loaded company name exactly          |

## Related code

* Driver adapter: `drivers/tally/`
* Canonical surface: `schemas/canonical/finance/`
