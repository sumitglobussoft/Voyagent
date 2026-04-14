# Architecture

> This document goes deeper than the [README](../README.md). Read the README first for the high-level picture.

## Core thesis

> **The AI is not the hard part. The adapter layer is.**

Voyagent is, under the hood, two things bolted together:

1. A **vendor-agnostic travel + finance integration platform**. This is the moat.
2. An **agentic chat layer** on top. This is the interface.

If we get (1) right, (2) becomes prompt engineering and tool routing. If we get (1) wrong, no amount of agent cleverness will save the product. Every early engineering decision should serve (1).

## Layered architecture

### Layer 0 — Platform services

Multi-tenant foundation every other layer assumes:

- **Tenancy model** — one tenant per travel agency, with sub-tenant support for branches/desks where relevant.
- **Identity & RBAC** — roles include `agent`, `senior_agent`, `accountant`, `admin`, `auditor`. Permissions scoped to domains (ticketing/hotels/accounting) and actions (read / quote / book / issue / post / reconcile).
- **Audit log** — every side-effect tool call records actor, tenant, inputs, outputs, driver invoked, approvals, timestamps. Immutable and exportable for CA/auditor review.
- **Approval workflows** — configurable gates: "issue_ticket above ₹X requires senior_agent approval", "post_journal_entry always requires accountant confirmation".
- **Credential vault** — per-tenant encrypted storage for GDS credentials, airline IATA codes, accounting-software API tokens, payment-gateway keys. Per-tenant KMS keys; BYO-key option for enterprise tenants.
- **Observability** — structured logs, per-tool metrics, per-driver health dashboards, prompt/response traces for every agent turn.
- **Billing & entitlements** — which drivers a tenant can use, usage metering.

### Layer 1 — Canonical Domain Model

The single internal vocabulary every agent and tool speaks. **Vendors never leak upward** — no `AmadeusPNR` type exists outside the driver.

Core objects (non-exhaustive):

| Object | Purpose |
|---|---|
| `Enquiry` | A client request, any domain. Carries intent, requirements, and state. |
| `Client` | End customer of the agency. |
| `Passenger` | A traveler on an itinerary (adult / child / infant / senior). |
| `Passport` | Document linked to a passenger, with validity + issuing authority. |
| `Itinerary` | Ordered segments of travel (flight, hotel, transfer, activity). |
| `Fare` | Priced offer against an itinerary, with fare rules. |
| `PNR` | Booking record with a GDS/airline, canonicalized. |
| `Booking` | Confirmed purchase — may contain flights, hotels, transfers, visa. |
| `VisaFile` | Visa application with checklist, documents, appointment, status. |
| `Voucher` | Hotel / transport / activity confirmation document. |
| `Invoice` | Customer-facing bill. |
| `Receipt` | Proof of collection. |
| `JournalEntry` | Double-entry accounting record. |
| `LedgerAccount` | Chart-of-accounts node. |
| `BSPReport` | Weekly/fortnightly IATA BSP statement, parsed. |
| `Reconciliation` | Match report between Voyagent's internal records and an external statement (BSP / bank / card / supplier). |
| `Payment` | Inbound or outbound money movement. |
| `Document` | Any uploaded artifact (passport scan, bank statement, supplier invoice). |
| `Message` | Any inbound/outbound client communication (email, WhatsApp, SMS). |

Version this model strictly. Driver contracts break when the canonical model changes.

### Layer 2 — Driver / Adapter Layer

One driver per external system. Each driver implements one or more **capability interfaces** and publishes a **capability manifest**.

Capability interfaces (initial set):

- `FareSearchDriver` — search flights/fares across sources.
- `PNRDriver` — create, modify, cancel, queue-read, void, refund PNRs.
- `HotelDriver` — search, price, book, cancel hotels.
- `TransportDriver` — transfers, cars, ground arrangements.
- `VisaPortalDriver` — form fill, document upload, appointment booking, status tracking. Most implementations are **browser automation**, not API.
- `AccountingDriver` — chart-of-accounts read, journal-entry post, invoice create, statement read.
- `PaymentDriver` — collect via UPI/card/bank/link; disburse via NEFT/RTGS/card/cheque.
- `BSPDriver` — fetch and parse BSP statements; raise ADM/ACM.
- `CardDriver` — fetch statements, match transactions, initiate refunds.
- `BankDriver` — fetch statements, initiate transfers, reconcile.
- `MessagingDriver` — email, WhatsApp, SMS send; optionally read.
- `DocumentDriver` — OCR, form-parse, signature detection for passports and supporting docs.
- `StatutoryDriver` — GST filing, TDS filing, PF/ESI/PT portals.

A capability manifest example:

```jsonc
{
  "driver": "tally_prime",
  "version": "1.0.0",
  "implements": ["AccountingDriver"],
  "capabilities": {
    "chart_of_accounts.read": "full",
    "journal_entry.post": "supported_via_xml_import",
    "invoice.create": "supported",
    "bank_statement.read": "not_supported"
  },
  "transport": ["xml_over_http", "odbc"],
  "requires": ["desktop_host"],
  "tenant_config_schema": { /* json schema */ }
}
```

The orchestrator reads manifests at runtime to decide:
- Which driver to route a tool call to.
- Whether to offer graceful degradation ("I'll generate a Tally-importable XML file for you to import manually").
- Whether an action is disabled for a tenant ("this tenant's QuickBooks plan doesn't permit API-driven journal posting").

### Layer 3 — Tool Runtime

Canonical tools expose stable, agent-facing function signatures. Each tool:

- Takes canonical-model inputs, returns canonical-model outputs.
- Dispatches to one or more drivers based on tenant config + capability manifest.
- Declares **side-effect flags**:

```python
@tool(
    name="issue_ticket",
    side_effect=True,
    reversible=False,
    approval_required=True,
    approval_roles=["senior_agent"],
)
def issue_ticket(pnr: PNR, fare: Fare) -> Ticket: ...
```

The runtime enforces approval gates *before* the driver is invoked. No agent can bypass this by "just calling the function."

Reversibility matters: `hold_booking` (reversible) may autorun; `issue_ticket` (irreversible) never does.

### Layer 4 — Agents

- **Orchestrator agent**
  - The chat entrypoint.
  - Classifies intent against the three domains.
  - Maintains per-entity conversation memory (per enquiry, per PNR, per invoice batch).
  - Routes to domain agents; hands back when the sub-task completes.
  - Owns the approval-gate UX — presenting irreversible actions to the user and capturing confirmation.

- **Domain agents**
  - `ticketing_visa` — owns the workflow state machine `enquiry → eligibility → quote → book → deliver → post-sale`.
  - `hotels_holidays` — owns `enquiry → multi-supplier quote → package → confirm → voucher → post-sale`.
  - `accounting` — owns `billing → collection → supplier payment → reconcile → report → file`.
  - Each domain agent is effectively a long-running state machine with tool access scoped to that domain.

- **Cross-cutting agents**
  - `document_verifier` — OCR + rule checks on passports, finances, travel history. Produces a structured verdict, not prose.
  - `reconciler` — matches Voyagent records against BSP / bank / card / supplier statements. Flags discrepancies with evidence.
  - `reporter` — generates sales / outstanding / profit / GST / TDS reports on demand.

Keep agent count small. The temptation to spawn one agent per activity is a trap — deep, brittle handoffs and duplicated plumbing. A thin orchestrator plus fat tools is easier to evolve.

### Layer 5 — Clients

**Desktop app** (candidate frameworks: Tauri, Electron)
- Runs a local agent runtime and driver host.
- Required for desktop-only drivers: GDS terminal sessions (Amadeus Selling Platform, Sabre Red, Galileo Smartpoint), Tally ODBC/XML-over-HTTP, smart-card readers, local ticket/voucher printers.
- Bridges to cloud for shared state, audit log, credentials, and agent context that must survive across devices.

**Web app** (candidate framework: Next.js / Remix / SvelteKit)
- Thin SPA against the cloud runtime.
- Cannot run desktop-bound drivers — degrades gracefully ("this action requires your desktop agent, which is offline").

**Mobile app** (candidate framework: React Native / Expo)
- Reports, approvals, inbound client message triage.
- Remote-control relay: pair with a desktop session over WebSocket, push commands to desktop, stream results back. Desktop is the executor; mobile is the steering wheel.

## Cross-cutting concerns

### Human-in-the-loop

Three levels:

- **Autopilot** — read-only or trivially reversible tools (search, quote, draft). No confirmation.
- **Review** — side-effect but reversible (hold booking, draft invoice). Single-click confirm.
- **Gated** — irreversible (issue ticket, submit visa, post journal entry, send payment). Explicit confirmation with a full diff of what will happen, who approved, and which driver will execute.

Confirmation is captured in the audit log regardless of level.

### Browser-automation subsystem

Many visa portals, some airline extranets, and several statutory portals have no API. A dedicated subsystem handles these:

- Playwright-based, with retryable flows.
- Session pool per tenant (many portals lock sessions per IP).
- CAPTCHA strategy (human-in-the-loop pass-through for now; optional solver later).
- Failure recording: every failed run captures screenshots + DOM snapshot for human review.

Treat this as first-class infrastructure, not a hack.

### Reconciliation engine

BSP / bank / card / supplier reconciliation is where Voyagent earns credibility with accountants. Requirements:

- Deterministic match rules, not "LLM said so."
- Confidence scores on fuzzy matches, always with evidence.
- Every unmatched item is actionable — classify it (missing invoice, billing error, refund due, commission under-paid) and create a task.
- Reports exportable in formats Tally/Zoho/auditors expect.

LLMs are used for *narration* of reconciliation findings, not for the matching itself.

### Data residency & compliance

- **India-first target (likely):** DPDP Act 2023, GST rules, TDS rules, BSP India rules.
- **Card data:** minimize PCI scope by tokenizing with the payment gateway; never store raw PANs.
- **Credentials:** per-tenant KMS-encrypted, never logged.
- **PII:** passport scans, financial documents — encrypted at rest, retention policy per tenant.

## Anti-patterns to avoid

- **One agent per activity.** Leads to brittle handoffs, duplicated plumbing, and huge prompt cost. Use domain agents plus tools.
- **Letting vendor types leak into agents.** If `issue_ticket` takes an `AmadeusPNR`, the abstraction is broken. Fix it at the driver boundary.
- **Agent-authored side effects without approval gates.** Any path where an LLM hallucination can post a journal entry or issue a ticket is a catastrophic bug.
- **Mocking BSP or bank data in reconciliation tests.** Integration tests must hit real (sandbox) systems. Mock/prod divergence is how reconciliation products die.
- **Building for one GDS "for now."** The whole value prop depends on vendor-agnosticism. Starting single-vendor is fine — locking to single-vendor assumptions in the canonical model is not.

## First vertical slice (pre-build plan)

Target flow, end-to-end:

> Flight enquiry → quote → ticket issue → invoice → BSP reconciliation

Scope:

- One `FareSearchDriver` + `PNRDriver`: **Amadeus**
- One `AccountingDriver`: **Tally**
- One `BSPDriver`: **BSPlink / IATA India**
- Orchestrator + `ticketing_visa` + `accounting` domain agents.
- Desktop client only (web/mobile deferred).
- No multi-tenancy beyond single tenant.

Success criteria:

- A real enquiry can flow end-to-end without leaving the chat.
- An issued ticket produces a Tally journal entry that reconciles cleanly against the weekly BSP statement.
- Swapping Amadeus for a Sabre driver later is purely additive.

If this slice holds up, the rest of Voyagent is mostly more drivers and more prompts.
