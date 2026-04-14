# Voyagent

**The Agentic Travel OS.**
*One chat. Every GDS, every accounting system, every workflow.*

> **Status:** Planning phase. No code yet. This repository currently captures the product vision, scope, architecture, and open questions so the team can align before building. See [docs/](./docs/) for deeper material.

---

## 1. What is Voyagent?

Voyagent is an agentic operating system for travel agencies. It replaces the manual, repetitive, multi-tool workflows that travel agency staff perform every day — ticketing, visa processing, hotel & holiday packaging, accounting, BSP reconciliation, GST/TDS compliance — with an intelligent **chat interface backed by specialized AI agents** that actually do the work end to end.

Think of it as "Claude Code, but for a travel company." The employee types or speaks what they need (*"Quote a Dubai 4-night package for 2 adults on the 22nd with Emirates direct, 4-star near Downtown"*) and the system drives the full workflow across whatever GDS, hotel bank, payment gateway, visa portal, and accounting software the agency happens to use.

## 2. The problem we are solving

A travel agency today juggles:

- **Multiple GDSes** (Amadeus, Sabre, Galileo/Travelport) plus consolidator portals (TBO, Riya, etc.) and direct airline/NDC feeds.
- **Multiple hotel / land-package sources** (Hotelbeds, TBO Hotels, direct contracts).
- **Multiple visa portals** (VFS Global, BLS, embassy/consulate sites — many without APIs).
- **Multiple payment rails** (UPI, NEFT/RTGS, card, payment links, BSP).
- **Multiple accounting stacks** (Tally, Zoho Books, Busy, QuickBooks, SAP, Marg, custom ERPs).
- **Manual reconciliation** against BSP statements, card statements, bank statements, supplier statements.
- **Statutory workload** (GST filings, TDS, PF/ESI, annual returns, audits).

Staff switch between 8–15 tools a day, copy-paste data, and re-key the same passenger, fare, and invoice information into each one. The work is **well-defined, rule-heavy, and highly repeatable** — ideal territory for agents.

## 3. Product scope

Voyagent replaces ops across **three functional domains**, drawn from the actual activity inventory of a working travel agency. The full verbatim activity list is in [docs/ACTIVITIES.md](./docs/ACTIVITIES.md).

### 3.1 Ticketing & Visa
Enquiry intake → passport/visa eligibility checks → document checklist generation → fare search across GDS/consolidators → quotation → booking/PNR → ticket issuance → visa form filling, appointment, biometrics, tracking → web check-in → schedule-change handling → cancellation & refund.

### 3.2 Hotels & Holidays
Enquiry intake → multi-supplier hotel + transport rate gathering → package costing → quotation → revisions → booking confirmation → voucher issuance → post-booking support. Covers FIT hotels, land arrangements, tours, Umrah land packages, and custom holiday building for any destination.

### 3.3 Accounting & Finance
Invoicing, collections (UPI/card/bank/cash/payment links), supplier payments (NEFT/RTGS/cheque/card), ledger entries, commission tracking, incentive billings, BSP reconciliation, ADM/ACM handling, card & bank reconciliation, chargebacks, GST computation & filing, TDS deduction & return filing, payroll statutory deductions, audit-ready books, and management reporting (sales / outstanding / profit per booking).

### 3.4 Three capability tiers (applies across all domains)
1. **Identify & Collect** — structured intake of requirements and documents via chat.
2. **Verify** — rule-based + LLM verification (passport validity, document completeness, fare legality, reconciliation matches).
3. **Act** — side-effecting tools that actually issue tickets, post journal entries, submit visa applications, send payments. All irreversible actions are gated behind explicit human confirmation.

## 4. Hard requirements

These are non-negotiable and shape every architectural decision:

- **GDS-agnostic.** Must work with every GDS and fare source in the market — not pick one. Amadeus, Sabre, Galileo/Travelport, TBO, Riya, consolidator XML feeds, airline NDC, LCC aggregators, and whatever comes next.
- **Accounting-software-agnostic.** Must work with every accounting system the agency may already use — Tally, Zoho Books, Busy, QuickBooks, SAP, Marg, custom ERPs.
- **Full ops replacement.** Not an add-on. Not a copilot. The goal is to retire the manual, multi-tool workflow entirely.
- **Tri-platform delivery.** Web (light users), Desktop (power users, where GDS terminals and Tally live), Mobile (reporting + remote-control of a paired desktop session).
- **Anyone can use it.** No assumptions about team size or employee count. Single-user up to many-users-per-tenant.
- **Auditable.** Every side-effect action is logged with actor, inputs, outputs, and approval trail.
- **India-first, globalization-safe.** The first market is India (BSP India, GST, TDS, UPI, Tally dominance, DPDP Act). The architecture makes no India-only assumptions: currency, tax, statutory filings, addresses, phone, identity documents, payment rails, language, and data residency are all abstracted for later expansion. See [D8](./docs/DECISIONS.md#d8--india-first-go-to-market-global-ready-architecture).

## 5. Architecture (6 layers)

The adapter layer — not the AI — is the platform's primary engineering asset. If we get vendor-agnosticism right, onboarding a new GDS or accounting system is a driver, not a redesign.

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 5 — Clients                                               │
│    Web SPA  ·  Desktop (Electron/Tauri)  ·  Mobile               │
├──────────────────────────────────────────────────────────────────┤
│  Layer 4 — Agents                                                │
│    Orchestrator  ·  Domain agents (ticketing_visa,               │
│    hotels_holidays, accounting)  ·  Cross-cutting agents         │
│    (document_verifier, reconciler, reporter)                     │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3 — Tool Runtime                                          │
│    Canonical tools (search_flights, issue_ticket,                │
│    post_journal_entry, reconcile_bsp, ...) with side_effect      │
│    and reversible flags for approval gating                      │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2 — Driver / Adapter Layer                                │
│    FareSearchDriver · PNRDriver · HotelDriver · VisaPortalDriver │
│    AccountingDriver · PaymentDriver · BSPDriver · CardDriver     │
│    MessagingDriver · ... (capability manifests per driver)       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 1 — Canonical Domain Model                                │
│    Enquiry, Passenger, Itinerary, Fare, PNR, Booking, VisaFile,  │
│    Voucher, Invoice, JournalEntry, LedgerAccount, BSPReport,     │
│    Reconciliation, ...                                           │
├──────────────────────────────────────────────────────────────────┤
│  Layer 0 — Platform Services                                     │
│    Multi-tenancy · RBAC · Audit log · Approval workflows ·       │
│    Credential vault · Observability · Billing                    │
└──────────────────────────────────────────────────────────────────┘
```

### 5.1 Canonical Domain Model (Layer 1)
One internal schema that every agent and tool speaks. Vendor-specific fields never leak upward. Adding a new GDS means writing a driver that maps its API to canonical `Fare` / `PNR` / `Booking` — the agents don't change.

### 5.2 Driver / Adapter Layer (Layer 2)
One driver per external system, each implementing a capability interface and declaring a **capability manifest** (what it can and cannot do). The orchestrator selects drivers at runtime based on tenant configuration and capability availability — so if a tenant's accounting software can't auto-post journal entries, Voyagent gracefully degrades to generating a Tally-importable XML file instead.

### 5.3 Tool Runtime (Layer 3)
Canonical tools dispatch to configured drivers. Each tool carries:
- `side_effect: bool` — does it change external state?
- `reversible: bool` — can the action be undone?
- `approval_required: bool` — must a human confirm before execution?

Irreversible side-effects (ticket issuance, payment, visa submission, journal posting) always require explicit confirmation.

### 5.4 Agents (Layer 4)
- **Orchestrator** — chat entrypoint, intent classification, routing, per-enquiry/PNR/invoice conversation memory.
- **Domain agents** — `ticketing_visa`, `hotels_holidays`, `accounting`. Each owns its workflow state machine: *enquiry → quote → book → deliver → post-sale*.
- **Cross-cutting agents** — `document_verifier` (OCR + rule checks on passports, finances, supporting docs), `reconciler` (BSP / card / bank / supplier matching), `reporter` (sales / outstanding / profit / GST / TDS reports).

### 5.5 Clients (Layer 5)
- **Desktop app** — heavy client. Hosts integrations that need local OS access: GDS terminal sessions (Amadeus Selling Platform, Sabre Red, Galileo Smartpoint), Tally ODBC/XML-over-HTTP, smart-card readers, local ticket/voucher printers.
- **Web app** — thin SPA for light users. Capabilities degrade gracefully where a driver is desktop-only.
- **Mobile app** — reports, approvals, and a remote-control relay that pairs to a desktop session over WebSocket. Desktop is the executor; mobile is the steering wheel.

### 5.6 Platform Services (Layer 0)
Multi-tenancy, RBAC (agent / senior agent / accountant / admin roles), audit log for every side-effect tool call, approval workflow engine, per-tenant credential vault for vendor credentials.

## 6. Naming & positioning

- **Product name:** **Voyagent**
- **Category line:** *The Agentic Travel OS*
- **Tagline options:**
  - *One chat. Every GDS, every accounting system, every workflow.*
  - *Travel ops, on autopilot.*

Positioning rationale in [docs/DECISIONS.md](./docs/DECISIONS.md#naming).

## 7. Known risks

Ranked roughly by impact:

1. **Integration surface area.** GDS, accounting, BSP, VFS, payment — this will dwarf the AI work. The adapter pattern is bet-the-company-on-it.
2. **Browser automation for portals without APIs.** VFS Global, some embassy sites, some airline extranets. Needs a dedicated Playwright-based sub-system with retry, session handling, and CAPTCHA strategy.
3. **Tally integration specifically.** Dominant in the Indian market, notoriously awkward interop (XML over HTTP, ODBC, TDL). Budget serious time here.
4. **BSP reconciliation precision.** This is where accountants will judge the product. Must be exact, not "AI-flavored."
5. **Compliance & credential scope.** Storing GDS, accounting, card and payment credentials per tenant puts us in DPDP (India) and PCI-DSS territory from day one.
6. **Human-in-the-loop design for irreversible actions.** Getting the confirmation UX right — stringent enough to prevent mistakes, loose enough to not be annoying.

## 8. First milestone (before writing any agent code)

**One vertical slice, end to end:**

> Flight enquiry → quote → ticket issue → invoice → BSP reconciliation

- **One GDS driver:** Amadeus
- **One accounting driver:** Tally
- **Full stack:** canonical domain model + two drivers + tool runtime + orchestrator + desktop client.

This proves the adapter pattern. After this, adding Sabre or Zoho Books becomes a driver, not a redesign.

## 9. Open questions (to resolve before build start)

1. **Canonical domain model v0.** Draft Pydantic v2 models in `schemas/canonical/` including `Money`, `TaxLine`, `TaxRegime`, `NationalId`, country-scoped `Address` from the first pass (see [D8](./docs/DECISIONS.md#d8--india-first-go-to-market-global-ready-architecture)).
2. **Credential vault & multi-tenant isolation model.** Per-tenant KMS? BYO-key option for enterprise customers?
3. **Auth provider.** Clerk vs WorkOS vs Ory. Decide when the first protected route is scaffolded.
4. **Pricing & packaging signal.** Influences whether Voyagent should also be single-binary (self-hosted-friendly) or cloud-only.

**Resolved:**
- ~~Market focus — India-first or global from day one?~~ **India-first go-to-market, globalization-safe architecture from day one.** See [D8](./docs/DECISIONS.md#d8--india-first-go-to-market-global-ready-architecture).
- ~~Tech stack & repo layout.~~ **TypeScript frontends (Next.js web, Tauri 2 desktop, Expo mobile) + Python agent/driver runtime (FastAPI, Pydantic v2, Temporal, Playwright). pnpm + Turborepo monorepo with a uv workspace for Python.** See [D9](./docs/DECISIONS.md#d9--tech-stack-typescript-frontends--python-agentdriver-runtime) and [STACK.md](./docs/STACK.md).
- ~~Agent runtime choice.~~ **Anthropic Python SDK with prompt caching enabled from day one, wrapped in our own orchestrator + domain-agent state machines.** See [D9](./docs/DECISIONS.md#d9--tech-stack-typescript-frontends--python-agentdriver-runtime).

## 10. Repository layout (planned)

Concrete layout and package naming are in [docs/STACK.md](./docs/STACK.md). High-level shape:

```
voyagent/
├── README.md                  ← you are here
├── LICENSE
├── pnpm-workspace.yaml        ← (planned) JS workspace root
├── pyproject.toml             ← (planned) uv workspace root
├── turbo.json                 ← (planned) pipeline graph
├── docs/
│   ├── ACTIVITIES.md          ← verbatim activity inventory from the customer
│   ├── ARCHITECTURE.md        ← deep-dive on the 6-layer architecture
│   ├── DECISIONS.md           ← decision log
│   └── STACK.md               ← tech stack + repo layout + tooling
├── apps/                      ← (future) web (Next.js), desktop (Tauri 2), mobile (Expo)
├── packages/                  ← (future) @voyagent/core, ui, chat, sdk, config, icons
├── services/                  ← (future) api, agent_runtime, worker, browser_runner
├── drivers/                   ← (future) one package per GDS / accounting / portal / rail
├── schemas/canonical/         ← (future) Pydantic v2 — the single source of truth
└── infra/                     ← (future) docker, terraform, codegen scripts
```

Only the root files and `docs/` exist today. Everything else is planned, not built.

## 11. Contributing

We are in the planning phase. The most valuable contributions right now are:

- Critiques of the architecture (especially the adapter-first bet).
- Concrete experience integrating with Tally, Amadeus, Sabre, TBO, VFS, or BSP.
- Draft canonical schemas for any domain object listed above.
- Prior-art pointers — especially failed or partially-successful attempts at travel-agency ERP/AI products.

Open a GitHub issue with the `planning` label or start a discussion.

## 12. License

See [LICENSE](./LICENSE).
