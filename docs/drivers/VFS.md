# VFS Global driver

VFS Global operates visa application centres on behalf of dozens of
consulates. The Voyagent VFS driver automates appointment search,
slot booking, and application status checks — the three most
repetitive tasks in a visa ops workflow.

Because VFS does not expose a modern public API, this driver uses a
**supervised browser automation** approach (Playwright, behind a
human-in-the-loop guard) rather than HTTP calls. Every action routes
through the approvals inbox before execution — no silent bookings.

Cross-reference:
* Full onboarding timeline → [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md)
* Driver index → [`../DRIVERS.md`](../DRIVERS.md)

## Setup

1. The agency must already have a **corporate VFS login** for the
   country/consulate pair they want to automate. VFS issues these via
   the consulate — there is no self-service signup.
2. Store the credentials in the Voyagent secret vault (not env vars
   — VFS creds rotate and per-country secrets are common):

   ```
   Secret path: tenants/<tenant_id>/vfs/<country_code>
   Keys:        username, password, corporate_id
   ```

3. Set the global env:

   ```bash
   export VOYAGENT_VFS_HEADLESS=true
   export VOYAGENT_VFS_PROXY=http://proxy:8080   # optional
   ```

4. Restart the browser-runner sidecar (`services/browser-runner`).

## What works today

* **Appointment search** — given country + city + applicant count,
  scrape the VFS slot calendar and return available dates.
* **Hold-and-confirm** — reserve a slot and route to approvals. A
  human approves (or rejects) before the booking is finalised.
* **Status check** — poll an application reference and return the
  current tracking status.

## What doesn't work yet

* **Form auto-fill** — we don't yet push applicant data into the VFS
  application form. That happens in a later release.
* **Biometric rescheduling** — VFS exposes this in the UI but we
  haven't wired the automation.
* **Non-standard VFS countries** — the DOM changes country-by-country;
  only a handful of countries are currently hand-tuned.

## Operational notes

* **Rate-limiting** — VFS aggressively rate-limits scraping. The
  driver spreads calls over a minimum 30 s interval and backs off
  exponentially on CAPTCHA.
* **CAPTCHA** — if a CAPTCHA is presented, the driver **stops** and
  surfaces an approval-inbox item so a human can solve it in a
  proxied iframe. We do not solve CAPTCHAs.
* **Session expiry** — VFS sessions time out after ~20 minutes of
  idle. The driver re-logs in automatically.

## Troubleshooting

| Symptom                              | Likely cause                              | Fix                                                |
| ------------------------------------ | ----------------------------------------- | -------------------------------------------------- |
| `Element not found: #slot-calendar` | VFS changed the DOM for that country      | Update the country-specific selectors              |
| CAPTCHA loop every call              | Too much load from one IP                 | Rotate via `VOYAGENT_VFS_PROXY`, slow down the tempo |
| `Session expired` after 20 min       | Normal — driver should re-login            | Check the browser-runner logs for re-auth failures |
| Slot held but never confirmed         | Approval never resolved; VFS released it | Shorten the approval SLA in tenant settings        |

## Related code

* Driver adapter: `drivers/vfs/`
* Browser automation: `services/browser-runner`
* Canonical surface: `schemas/canonical/visa/`
