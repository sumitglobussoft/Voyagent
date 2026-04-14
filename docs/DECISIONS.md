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
