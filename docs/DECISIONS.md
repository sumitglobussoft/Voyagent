# Decision Log

A running record of product and architectural decisions made during planning, including the options considered and the reasoning behind each pick. New decisions append to the bottom.

---

## D1 — Customer problem is full ops replacement, not copilot

**Date:** 2026-04-14
**Status:** Accepted

**Context.** The customer is a working travel agency with a detailed activity inventory across ticketing & visa, hotels & holidays, and accounting. Work is manual, repetitive, and spans 8–15 tools per day.

**Decision.** Voyagent replaces the existing ops end to end. It is not an add-on to existing software, not a chatbot layered on a CRM, not a copilot that drafts emails. The success bar is "the agency stops using the old workflow."

**Consequences.**
- We must eventually cover *all* of the activities in [ACTIVITIES.md](./ACTIVITIES.md), not a subset.
- Irreversible actions (ticket issuance, payments, visa submission, journal posting) must be first-class and safe.
- The product must be trustworthy enough for accountants, not just sales agents.

---

## D2 — Vendor-agnostic across GDS and accounting

**Date:** 2026-04-14
**Status:** Accepted

**Context.** Customer explicitly required: *"should be working with every GDS and every accounting software in the market."*

**Decision.** Voyagent is vendor-agnostic at the adapter layer. Agents and tools speak only the canonical domain model; every external system is a driver that translates.

**Alternatives considered.**
- *Pick one GDS + one accounting stack (e.g., Amadeus + Tally) for v1.* Rejected as the project's default posture — we will still *start* with that slice, but the architecture assumes many more from day one.
- *Use a third-party travel aggregator API (e.g., TBO) as the GDS abstraction.* Rejected: we'd inherit its limits, fees, and vendor politics.

**Consequences.**
- The adapter layer is the primary engineering asset, not the AI.
- Canonical domain model versioning becomes load-bearing.
- Adding a new GDS or accounting system is a driver, not a redesign.

---

## D3 — Three deployment targets: web, desktop, mobile

**Date:** 2026-04-14
**Status:** Accepted

**Context.** Customer specified: web for light users, desktop for power users, mobile mainly for reporting and remote-connecting to the desktop.

**Decision.**
- **Desktop is the heavy client.** It hosts drivers that require local OS access (GDS terminals, Tally ODBC, smart-card readers, local printers).
- **Web is a thin SPA.** It degrades gracefully when a driver is desktop-only.
- **Mobile is reports + remote control.** It pairs to a desktop session and pushes commands over WebSocket.

**Consequences.**
- We need a desktop agent runtime (likely Tauri or Electron) from early in the roadmap.
- We need a pairing / relay protocol between mobile and desktop.
- "Cloud-only" is not a viable topology; the architecture must support a split runtime.

---

## D4 — Thin orchestrator + fat tools, not one agent per activity

**Date:** 2026-04-14
**Status:** Accepted

**Context.** The activity inventory has 100+ discrete activities. A tempting but wrong architecture is one agent per activity.

**Decision.** Three domain agents (`ticketing_visa`, `hotels_holidays`, `accounting`) plus a chat orchestrator and a few cross-cutting agents (`document_verifier`, `reconciler`, `reporter`). All heavy lifting happens in canonical tools, not in agent-to-agent handoffs.

**Reasoning.**
- Deep per-activity agent trees produce brittle handoffs and duplicated plumbing.
- Orchestrator routing quality *is* the bottleneck either way — better to invest there.
- With one travel company and three domains, the thin-orchestrator shape is adequate and cheaper to iterate on.

**Consequences.**
- The canonical tool set has to be expressive — sparse tools would force logic back into the agents.
- Approval gates live in the tool runtime, not in the agents, so no amount of prompt-engineering bypasses them.

---

## D5 — Three capability tiers: Identify & Collect, Verify, Act

**Date:** 2026-04-14
**Status:** Accepted

**Context.** The customer's own activity list gestures at these three tiers at the end of the Ticketing section.

**Decision.** Every workflow is a pipeline through three tiers:
1. **Identify & Collect** — structured intake via chat.
2. **Verify** — rule-based + LLM checks on documents, fares, reconciliation matches.
3. **Act** — side-effecting tools, gated by human confirmation for irreversible actions.

**Consequences.**
- Each canonical tool is tagged by tier; Act tools carry `side_effect`, `reversible`, and `approval_required` flags.
- Verify is the highest-leverage tier for AI — rule-heavy, pattern-matching, low-risk.
- The same Verify primitives show up across domains (e.g., passport expiry check appears in both ticketing and hotels).

---

## D6 — Name: Voyagent, category: "Agentic Travel OS"

**Date:** 2026-04-14
**Status:** Accepted

**Context.** We considered several descriptive names (Agentic Travel MIS, Travel ERP with AI, Travel Ops Copilot) and brandable marks (Voyagent, Itin, Trevo, Navra, Plyr, Kairo).

**Decision.** Product name: **Voyagent.** Category line: *The Agentic Travel OS.*

**Reasoning.**
- "MIS" undersells — we are not a reporting tool.
- "ERP" is the category the buyer already budgets for, but it signals heavy and slow.
- "Copilot" caps TAM to "assistant" pricing.
- "OS" matches the replace-ops ambition and leaves room to expand.
- "Voyagent" is short, pronounceable, literally encodes "voyage" + "agent", and is trademark-viable.

**Tradeoff accepted.** Calling it an "OS" raises buyer expectations for adjacent capabilities (CRM, HR, payroll). We accept that scope pressure because it matches the actual ambition.

**Follow-ups.**
- Confirm `voyagent.com` / `.ai` / `.app` domain availability.
- Trademark search in India and target international markets.

---

## D7 — Out of scope (for now)

**Date:** 2026-04-14
**Status:** Accepted

Not part of v1 scope, explicitly deferred:

- **Corporate travel self-booking tools (SBTs)** for the agency's own corporate clients. Voyagent is for the agency's staff, not their clients' travelers.
- **Generic CRM features.** Lead scoring, marketing automation, campaign management — a different product.
- **HR / payroll beyond statutory deductions.** Salary calc and PF/ESI/PT are in scope because they're in the accounting activity list; full HRIS is not.
- **Consumer-facing booking site.** Voyagent powers the agency; a B2C storefront is a separate product that could consume the same APIs later.

Revisit when a clear customer pull exists.

---

## D8 — India-first go-to-market, global-ready architecture

**Date:** 2026-04-14
**Status:** Accepted

**Context.** The target first market is India — dominated by Tally, TBO/Riya consolidators, BSP India, GST, TDS, UPI, and DPDP Act compliance. But the long-term ambition is global: UK, UAE, Southeast Asia, and beyond.

**Decision.**
- **Go-to-market is India-first.** Early drivers, compliance work, payment rails, and support hours optimize for Indian travel agencies.
- **The architecture is globalization-safe from day one.** No core abstraction — canonical model, drivers, tool runtime, platform services — may assume India. Country-specific rules live behind country/region-scoped driver implementations and per-tenant configuration, never in shared types or hard-coded logic.

**Concretely, this means:**

1. **Currency** — every monetary field carries an ISO-4217 currency code. No bare `amount: number` fields. Default tenant currency is configurable; multi-currency bookings/invoices are first-class.
2. **Tax** — GST is one implementation of a generic `TaxRegime` interface. VAT, SST, HST, EU VAT-OSS, UAE VAT, and others plug in as peers. No `gst_rate` field in the canonical model — use `tax_lines: TaxLine[]` with a regime tag.
3. **Statutory filings** — GST/TDS/PF/ESI filings live behind a `StatutoryDriver` interface (D2 already anticipated this). HMRC, IRS 1099, Singapore IRAS, etc. are drivers, not special cases.
4. **Identity documents** — passport is the universal canonical traveler identity. Aadhaar/PAN are stored as typed, optional `NationalId` entries keyed by country; they never appear in required fields of `Passenger` or `Client`.
5. **Addresses** — generic `Address` with locale-typed subfields (no hard-coded "state" / "PIN"). Validators plug in per country.
6. **Phone numbers** — E.164 always. No Indian-format assumptions in storage or display.
7. **Payment rails** — UPI / NEFT / RTGS are implementations of `PaymentDriver`. SEPA, ACH, Wise, Stripe Connect, local wallets slot in later without touching the tool runtime.
8. **Dates, times, numbers** — UTC storage, locale-driven rendering. Indian lakhs/crores formatting is a presentation-layer concern, not a model concern.
9. **Language** — English-first UI, but every user-facing string in the product (including agent-authored replies) passes through an i18n layer so Hindi, Arabic, and others can be added without forking prompts or UI.
10. **Data residency** — tenant configuration includes a data-residency region. The platform services layer (storage, logs, credentials) must support multi-region from the start, even if we deploy only `ap-south-1` on day one.
11. **Compliance envelope** — DPDP is the v1 compliance baseline, but the audit log, credential vault, consent tracking, and retention policies are designed to also satisfy GDPR and UAE PDPL without rework.
12. **BSP** — IATA BSP is natively global (different settlement cycles per country). `BSPDriver` is already country-scoped; no change needed.

**What we are *not* doing now (but the architecture permits):**
- Shipping non-INR currencies in v1 UI.
- Supporting non-India statutory filings in v1.
- Multi-region deployment — we deploy in one region for India, but with the plumbing to add more.
- Localization beyond English — but every string is i18n-ready.

**Consequences.**
- Slightly more upfront modeling work (tax lines, national IDs, currency on every money field). Worth it — retrofitting these is brutal.
- Every driver and every migration must be reviewed for hidden India assumptions before merge.
- Documentation and examples deliberately show at least one non-India scenario so the abstractions don't silently decay into India-only.

**Follow-ups.**
- Canonical model v0 must include `Money`, `TaxLine`, `TaxRegime`, `NationalId`, and country-scoped `Address` from the first draft.
- Linter/CI rule: reject PRs that introduce `inr`, `gst`, `aadhaar`, `pan`, or `pincode` in shared code outside clearly country-scoped modules.
- Design doc for the i18n layer before any user-facing string ships.

---

## D9 — Tech stack: TypeScript frontends + Python agent/driver runtime

**Date:** 2026-04-14
**Status:** Accepted

**Context.** We needed a stack that maximizes code sharing across web / desktop / mobile, gives us the strongest ecosystem for the integration-heavy driver layer, and keeps the canonical domain model single-sourced across languages.

**Decision.**

**Frontends — all TypeScript/React:**
- **Web:** Next.js (App Router) — SSR + streaming for chat.
- **Desktop:** Tauri 2 (Rust shell) with a Vite + React frontend — small binary, low memory, clean plugin story for OS-native drivers.
- **Mobile:** React Native + Expo (EAS for builds) — reports + desktop remote-control relay.
- **Monorepo:** pnpm workspaces + Turborepo.
- **Shared UI:** Tamagui for cross-platform components where sensible; Radix + Tailwind elsewhere.

**Backend / agent runtime — Python:**
- **HTTP API:** FastAPI (REST + SSE for agent streaming).
- **Canonical model:** Pydantic v2 — the single source of truth; emits JSON Schema consumed by TS via `openapi-typescript` into `@voyagent/core`.
- **Agent loop:** Anthropic Python SDK with prompt caching enabled from day one.
- **Browser automation:** Playwright (Python) — first-class for visa/portal drivers.
- **Long-running workflows:** Temporal — visa tracking, BSP reconciliation, async driver retries.
- **Data:** PostgreSQL + Redis + S3-compatible object store.

**Drivers — primarily Python.** Desktop-bound drivers (Tally ODBC, smart-card readers, local printers) run as a local Python sidecar launched by the Tauri desktop app over a local socket.

**Alternatives considered.**
- *Pure TypeScript everywhere (Hono + tRPC backend, Node drivers).* Simpler team story, weaker Playwright + OCR + data ecosystem, and Anthropic's Python SDK has a slight agent-patterns lead. Rejected for the moat, kept as a fallback if hiring shape forces it.
- *Electron instead of Tauri.* More examples, bigger ecosystem, but 10× binary and higher memory footprint matter for a desktop power-user tool.
- *Flutter for all three clients.* Weaker web and agentic-chat UI ecosystem; code-sharing story with web-specific payment/auth SDKs is poor.
- *.NET MAUI / WinUI.* Would be sensible if Windows-only and Tally-first. We're neither — cross-platform desktop matters for global expansion.
- *Inngest / Hatchet instead of Temporal.* Lighter ops, smaller. Acceptable substitutes; not a day-one decision.

**Consequences.**
- Two-language stack → higher hiring bar, context-switch tax. Accepted for the ecosystem payoff.
- Pydantic → TS generation has edge cases (unions, discriminated types); `@voyagent/core` carries a thin hand-written adapter layer for the tricky bits.
- Tauri's ecosystem is smaller than Electron's — weird native deps may require writing Rust plugins. Acceptable cost.
- Temporal adds ops complexity early; if it bites, Inngest/Hatchet are drop-in-ish replacements.

**Follow-ups.**
- See [STACK.md](./STACK.md) for concrete repo layout, package names, entry points, build tooling, and the Pydantic → TS contract flow.
- Canonical model v0 (open question in README) is now "write Pydantic v2 models in `schemas/canonical` with the globalization primitives from [D8](#d8--india-first-go-to-market-global-ready-architecture)."
- Scaffold `pnpm-workspace.yaml`, `turbo.json`, and `pyproject.toml` at repo root as the first piece of executable work.

---

## D10 — Canonical domain model v0 landed

**Date:** 2026-04-14
**Status:** Accepted

**Context.** Every agent, tool, and driver needs a single vocabulary before any code can be written against the adapter layer ([D2](#d2--vendor-agnostic-across-gds-and-accounting)). The globalization contract ([D8](#d8--india-first-go-to-market-global-ready-architecture)) must be baked in from the first draft or we'll pay for it later.

**Decision.** Commit Pydantic v2 definitions under [`schemas/canonical/`](../schemas/canonical/) covering primitives, identity, travel, finance, and lifecycle. The first vertical slice (Amadeus + Tally + BSP India) will build against this spec.

**Scope delivered.**
- **Primitives:** `Money`, `TaxLine` + `TaxRegime`, `NationalId`, `Address`, `Phone`, `Email`, `LocalizedText`, `Period`, ISO-code aliases (`CountryCode`, `CurrencyCode`, `LanguageCode`, `IATACode`), `Gender`, `EntityId`, `Timestamps`.
- **Identity:** `Client` (with `TaxRegistration`), `Passenger`, `Passport`.
- **Travel — full:** `Itinerary`, `FlightSegment`, `Fare`, `PNR`, `Ticket`, `Booking`.
- **Travel — skeleton:** `HotelStay`, `HotelBooking`, `TransferSegment`, `VisaFile` + `VisaChecklistItem` (enough for drivers to start; fields will expand in v1).
- **Finance:** `Invoice`, `InvoiceLine`, `Payment`, `Receipt`, `LedgerAccount`, `JournalEntry` (with per-currency balancing invariant), `BSPReport`, `Reconciliation`.
- **Lifecycle:** `Enquiry`, `Document`, `AuditEvent`.

**Invariants encoded in the spec:**
- `Money` rejects `float`; arithmetic requires matching currencies.
- `TaxLine` uses `rate_bps` (basis points) — no float rate math anywhere.
- `Passport` date ordering and `Period` UTC-awareness are validated at the model layer.
- `JournalEntry` enforces debits == credits per currency.
- No India-specific fields anywhere in shared code. GST, PAN, Aadhaar, PIN are either `TaxLine` regime, `NationalId` entries, or free-form `Address` fields.

**Deferred to v1 (documented in [CANONICAL_MODEL.md](./CANONICAL_MODEL.md)):**
- Typed `Enquiry.requirements` per domain (currently `dict[str, Any]`).
- Tenant / User / Role types (blocked on auth provider decision).
- Structured fare rules and cancellation rules (free-form `LocalizedText` for now).
- FX / multi-currency rate primitives.
- Voucher type and full hotel/visa field sets.

**Alternatives considered.**
- *JSON Schema hand-authored first, Pydantic later.* Rejected — duplicates the source of truth and we'd end up generating JSON Schema from Pydantic anyway (per [D9](#d9--tech-stack-typescript-frontends--python-agentdriver-runtime)).
- *TypeScript-first canonical model with Zod / Valibot.* Rejected — drivers and agent runtime are Python per [D9]; Pydantic is the better fit and still yields TS types via the OpenAPI codegen.
- *Thinner v0 (primitives only).* Rejected — drivers can't start without the domain objects they'll produce/consume. v0 as landed is the minimum surface to unblock the first vertical slice.

**Consequences.**
- Drivers have a stable contract to build against before the agent runtime exists.
- Any change to these models between v0 and v1 must follow the evolution policy in [CANONICAL_MODEL.md](./CANONICAL_MODEL.md#evolution-policy).
- The CI codegen gate (`Pydantic → OpenAPI → @voyagent/core`) becomes a blocking check the moment `services/api` scaffolds.

**Follow-ups.**
- Wire `schemas/canonical` into `pyproject.toml` as a workspace member when we leave planning.
- Add the CI linter that rejects `inr`/`gst`/`aadhaar`/`pan`/`pincode` token leakage in non-India-driver code paths (see [D8](#d8--india-first-go-to-market-global-ready-architecture)).
- Write unit tests for the invariants (money-with-float rejection, journal balancing, period ordering, passport date ordering) before the first driver lands.

---

## Template for future entries

```
## D<N> — <Short decision title>

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded by D<N> | Rejected

**Context.** What forced the decision.

**Decision.** What we picked.

**Alternatives considered.** What else we looked at and why it lost.

**Consequences.** What this commits us to / what breaks if we change our minds.

**Follow-ups.** Concrete work this creates.
```
