# BSP India driver

BSP (Billing and Settlement Plan) is IATA's global settlement system
for ticket agencies. The BSP India driver ingests the weekly BSP
statement, reconciles it against Voyagent's ticket events, and flags
discrepancies for the agency's accountant to resolve.

This is **inbound-only** — Voyagent never writes to BSP.

Cross-reference:
* Full onboarding timeline → [`../VENDOR_ONBOARDING.md`](../VENDOR_ONBOARDING.md)
* Driver index → [`../DRIVERS.md`](../DRIVERS.md)

## Setup

BSPlink does not expose a modern API for India — the weekly statement
is delivered as a fixed-width or CSV file via a web download. The
driver supports two ingest modes:

1. **Manual upload** — the agency's accountant downloads the weekly
   BSP file from BSPlink and uploads it through Voyagent's
   `/app/bsp/upload` page. Simplest, zero credentials required.
2. **Scripted pull** (beta) — the driver logs into BSPlink with stored
   credentials and downloads the file on a schedule. Requires the
   agency's BSPlink login + 2FA token device access.

For the scripted pull:

```bash
export VOYAGENT_BSP_USERNAME=agent-iata-code
export VOYAGENT_BSP_PASSWORD=...
export VOYAGENT_BSP_IATA_NUMBER=1234567
export VOYAGENT_BSP_COUNTRY=IN
```

Restart `services/api`. The driver will attempt a weekly pull at the
scheduled time configured in tenant settings.

## What works today

* **HOT/REM parse** of the standard BSP India file layout.
* **Reconciliation** against issued tickets — matches by ticket
  number, commission, and net remittance amount.
* **Discrepancy report** — anything that doesn't reconcile gets an
  approval-inbox entry flagged for the accountant.

## What doesn't work yet

* **ADM/ACM workflows** — Agency Debit/Credit Memos are surfaced but
  can't yet be disputed through Voyagent. Agency still uses BSPlink
  directly for disputes.
* **Non-India BSPs** — the parser is hand-tuned to the India file
  format. Other BSPs (BSP UK, BSP UAE, ARC in the US) are separate
  driver work.
* **Real-time settlement** — weekly batch only; BSP itself doesn't
  settle faster.

## Troubleshooting

| Symptom                                   | Likely cause                              | Fix                                                |
| ----------------------------------------- | ----------------------------------------- | -------------------------------------------------- |
| Parser fails on a new row type             | IATA changed the HOT/REM layout           | Check BSPlink release notes, update the parser     |
| 100% of tickets show as discrepancies      | Wrong IATA number in tenant settings      | Fix `VOYAGENT_BSP_IATA_NUMBER`                     |
| Scripted pull fails with 2FA prompt        | BSPlink 2FA required                      | Fall back to manual upload                         |
| Commission amounts off by a paisa         | Rounding on Voyagent's side               | Check `schemas/canonical/finance/Money` decimals   |

## Related code

* Driver adapter: `drivers/bsp_india/`
* Canonical surface: `schemas/canonical/finance/`
