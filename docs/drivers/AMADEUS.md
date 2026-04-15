# Amadeus driver

The Amadeus driver connects Voyagent to the Amadeus GDS via the
**Self-Service APIs** for sandbox/development and the Enterprise APIs
for production. Self-Service is free, no-contract, and sufficient for
search + PNR creation — ticketing requires Enterprise.

Cross-reference:
* Full onboarding timeline → [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md)
* Driver index → [`../DRIVERS.md`](../DRIVERS.md)

## Self-service (sandbox) setup

1. Sign up at <https://developers.amadeus.com/>.
2. Create a new "self-service" workspace.
3. Generate an API Client ID + Secret pair for that workspace.
4. Set the environment variables on your API service:

   ```bash
   export VOYAGENT_AMADEUS_CLIENT_ID=your-client-id
   export VOYAGENT_AMADEUS_CLIENT_SECRET=your-client-secret
   export VOYAGENT_AMADEUS_ENV=test  # switch to "production" later
   ```

5. Restart the `services/api` process.
6. Verify by running a test search from the agent chat:

   > Find BOM→DXB flights on 2026-05-01 for 1 adult economy.

   You should see a list of fares come back with real airline codes.

## Production (Enterprise) setup

Production access is contract-gated and takes **2–6 weeks** to
provision. See [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md) for
the full checklist (IATA number, office ID, TIDS, etc.).

Once provisioned, set `VOYAGENT_AMADEUS_ENV=production` and restart the
API service. The client ID/secret point to the Enterprise endpoint and
now carry ticket-issuance authority.

## What works today

* **Flight fare search** — origin/destination/date → list of offers.
* **Flight offer pricing** — lock a quote for confirmation.
* **PNR creation** — self-service supports `flight-create-orders`.

## What doesn't work yet

* **Ticket issuance (TKT)** — needs Enterprise credentials and a valid
  IATA/BSP relationship.
* **Void/refund** — same blocker.
* **Ancillaries** (seats, bags) — not wired up in v0.
* **Schedule changes from the airline** — not streamed in; polled on a
  schedule instead.

## Troubleshooting

| Symptom                                       | Likely cause                                      | Fix                                                           |
| --------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------- |
| `401 Unauthorized` on first call              | Env vars not set or stale process                 | `echo $VOYAGENT_AMADEUS_CLIENT_ID`; restart `services/api`    |
| `38189: Authorization failed`                 | Using production env with self-service creds     | Set `VOYAGENT_AMADEUS_ENV=test`                               |
| Empty `data: []` on search                    | No inventory on that OD/date — expected           | Try a well-served route + date (BOM→DXB, +14 days)            |
| `429 Too Many Requests`                       | Self-service quota blown                           | Rate-limit or upgrade tier                                    |
| PNR create fails with `INVALID PASSENGER`     | Name or DOB formatting                             | Check against canonical model field rules                     |

## Related code

* Driver adapter: `drivers/amadeus/`
* Canonical surface: `schemas/canonical/flights/`
* Agent tools: see `services/agent-runtime` for the flight-search tool
  wiring.
