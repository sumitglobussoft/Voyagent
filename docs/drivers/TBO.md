# TBO Holidays driver

TBO is a major Indian travel consolidator (flights + hotels + holidays
+ transfers). The Voyagent TBO driver wraps their partner API so an
agency that already has a TBO account can search and book through
Voyagent without learning TBO's SOAP/XML surface.

Cross-reference:
* Full onboarding timeline → [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md)
* Driver index → [`../DRIVERS.md`](../DRIVERS.md)

## Sandbox setup

1. Contact your TBO account manager to request sandbox credentials
   for the Partner API. (There is no self-service sign-up — TBO is
   agency-only.)
2. TBO will return a `ClientId`, `Username`, and `Password`.
3. Set the environment variables on `services/api`:

   ```bash
   export VOYAGENT_TBO_CLIENT_ID=...
   export VOYAGENT_TBO_USERNAME=...
   export VOYAGENT_TBO_PASSWORD=...
   export VOYAGENT_TBO_ENV=test
   ```

4. Restart the API service.
5. Run a sandbox search from the agent chat:

   > Search hotels in Dubai 2026-05-10 to 2026-05-14, 2 adults 1 room.

## Production setup

Flip `VOYAGENT_TBO_ENV=production`. No new credentials — TBO uses the
same client ID across environments, only the API endpoint changes.

The timeline to production is **1–2 weeks** after your agency contract
is signed with TBO, which is faster than most GDSs because TBO doesn't
require IATA accreditation.

## What works today

* **Hotel search + book** — the TBO hotel inventory is the driver's
  flagship capability.
* **Flight search via TBO** — lower-touch than Amadeus; TBO aggregates
  multiple GDSs behind the scenes.
* **Holiday packages** — static packages, search only (booking is
  manual for now).

## What doesn't work yet

* **Hotel modifications** (date change, room change) — not surfaced.
* **Transfers** — canonical model exists but the driver isn't wired up.
* **Visa** — TBO does offer visa processing; not yet integrated.

## Troubleshooting

| Symptom                                       | Likely cause                                      | Fix                                                       |
| --------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------- |
| `Authentication failed`                       | Wrong `ClientId` / case-sensitive username        | Copy-paste from the TBO portal, watch for trailing spaces |
| Sandbox returns hotel results, prod does not  | `VOYAGENT_TBO_ENV` still set to `test`            | Switch to `production` + restart                          |
| `No Rooms Available`                          | Real inventory state, not a bug                    | Try different dates / destinations                        |
| Slow searches (>10 s)                         | TBO aggregator is genuinely slow on some routes    | Increase the driver's client timeout                      |

## Related code

* Driver adapter: `drivers/tbo/`
* Canonical surface: `schemas/canonical/hotel/`
