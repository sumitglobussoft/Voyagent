# Voyagent Implementation Plan

Living punch-list for the v0 alpha as of 2026-04-15. Pairs with [README.md](./README.md) (what exists), [CHANGELOG.md](./CHANGELOG.md) (what shipped when), and [docs/DECISIONS.md](./docs/DECISIONS.md) (why).

## 1. Shipped

Everything currently in `main`, grouped by domain. Most recent pushes (2026-04-15): `5e48322` (vendor onboarding doc), `b994465` (tier A polish), `903ed6f → 0600f04` (production bug fixes — /app loop, next= preservation, /api/contact 404), `02286a4` (audit hook + admin RBAC + UUIDv7), `c439755` (audit log viewer + desktop tabs + mobile typing), `ac41dc5 → 39f1350` (marketing alignment + /changelog + Playwright). Previous day's wrap was `8182e1a`.

### Recent additions (2026-04-15)

- **Audit log viewer** `/app/audit` with admin-RBAC gate (`require_agency_admin` rejects non-admins with `forbidden_role`), filterable by actor / kind / date range, inline JSON payload via `<details>`, kind-aware badge color map. `approval.granted` / `approval.rejected` events flow from the resolve endpoint into `audit_events.tool` (best-effort try/except so audit failure cannot roll back the approval state transition).
- **Vendor onboarding doc** at `/docs/VENDOR_ONBOARDING` and `docs/VENDOR_ONBOARDING.md` — client-facing per-vendor sign-up requirements (TBO, Amadeus, Tally, VFS, Hotelbeds).
- **Demo account** `demo@voyagent.globusdemos.com` exposed on `/app/sign-in` with a "Use demo credentials" pre-fill link (`?demo=1`); tenant deliberately isolated.
- **Three production bugs closed**: `/app` redirect loop (host nginx `return 308` → `proxy_pass` direct), middleware `next=` preservation (rewrote matcher + path normalization + `safeNextPath` open-redirect guard + reconstruct origin from `X-Forwarded-Host`), `/api/contact` 404 (added nginx `location = /api/contact` ahead of catch-all + real per-IP / per-email / global rate limiter in marketing route).
- **Open-redirect safety** wired through `apps/web/lib/next-url.ts::safeNextPath()` — rejects `//evil.com`, `https://`, `javascript:`, paths with backslashes or colons. Used at three layers: middleware, sign-in/sign-up pages, both server actions.
- **Playwright E2E**: 161 passed / 0 failed / 3 skipped (1.3 min) including `redirect-safety.spec.ts` with 8 hostile-shape parametrized tests (sign-in × sign-up × {//, https://, javascript:}).

### Auth (in-house)
- `POST /api/auth/sign-up`, `/sign-in`, `/refresh`, `/sign-out`, `GET /api/auth/me`.
- Argon2id password hashing; HS256 access JWT (1h TTL); opaque refresh token (30d, single-use rotation).
- Redis-backed JWT revocation via jti denylist.
- `users` + `auth_refresh_tokens` tables.
- `email_verified` gate enforced on sign-in, with two distinguishable 401 detail codes: `email_not_verified` vs `invalid_credentials`.
- Stub email-verification delivery: `POST /api/auth/send-verification-email` (logs link to stdout) and `POST /api/auth/verify-email` (Redis-backed token, 24h TTL).
- `VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION=true` is set on the prod host until a real delivery provider lands; new signups there are `email_verified=true` for now.

### Chat + agent runtime
- `POST /chat/sessions`, `GET /chat/sessions`, `POST /chat/sessions/{id}/messages` (SSE stream).
- Real Anthropic client with prompt caching; bounded exponential backoff on `RateLimitError`, `APIConnectionError`, and 5xx `APIStatusError` with `Retry-After` awareness.
- In-process orchestrator in `services/agent_runtime/src/voyagent_agent_runtime/orchestrator.py` streaming events to clients over FastAPI SSE.
- `ToolSpec.output_schema` validated at runtime, with one automatic repair-retry on schema failure.
- Approval-gated tool calls through `tools.py` + `_agent_loop.py`.
- Domain agents: `ticketing_visa`, `accounting`, `hotels_holidays`.

### Approvals
- `/api/approvals` (list, get, resolve) with lazy expiry sweep and cross-tenant → 404.
- `/app/approvals` page: pending inbox + recent history, Approve / Reject Server Actions.
- Postgres-backed `pending_approvals` with TTL and status enum; `resolve_approval` is tenant-scoped.
- Wire note: `payload` and `resolved_by_user_id` fields are always empty in v0 because the storage schema for them is deferred. The response shape is locked so the UI is stable.

### Enquiries
- `enquiries` table + `enquiry_status` enum (`new | quoted | booked | cancelled`, terminal states sticky).
- Migration `0006_enquiries`.
- Full CRUD: `POST /api/enquiries`, `GET /api/enquiries` (status / q search + pagination), `GET/PATCH /api/enquiries/{id}`, `POST /api/enquiries/{id}/promote-to-session`.
- UI: `/app/enquiries` list + filter + search, `/app/enquiries/new` create form, `/app/enquiries/{id}` detail + edit + promote-to-chat + two-step cancel.
- Nav links in `apps/web/app/layout.tsx`.
- New helper: `apps/web/lib/api.ts` (server-side authenticated fetch with cookie forwarding to the loopback nginx listener).

### Reports
- `GET /reports/receivables`, `/reports/payables`, `/reports/itinerary`, all tenant-isolated.
- Receivables and payables now read real data from `invoices` + `bills` + `journal_entries` with 0-30 / 31-60 / 61-90 / 90+ aging buckets computed server-side.
- Itinerary reads from the session store.

### Hotels
- Canonical types: `HotelRoom`, `HotelRate`, `HotelProperty`, `HotelSearchResult`, `BoardBasis` enum.
- `drivers/tbo/` HTTP wiring for search + check_rate; book/cancel/read raise `CapabilityNotSupportedError`.

### Drivers
- `drivers/_contracts/` capability Protocols + error types complete.
- `drivers/amadeus` partial (self-service sandbox), with JSON-decode failures mapped to `TransientError`.
- `drivers/tbo` partial (search + check_rate).
- `drivers/bsp_india` with the shipped 164-code IATA airline allow-list enforced on HAF rows; HAF parser trailing `\r` strip fix.
- `drivers/vfs` MFA selector now raises `PermanentError("mfa_required")` rather than `AuthenticationError`.
- `drivers/tally` skeleton.

### Storage
- Tables: `users`, `tenants`, `sessions`, `messages`, `pending_approvals`, `tenant_credentials`, `audit_events`, `auth_refresh_tokens`, `passengers`, `invoices`, `bills`, `ledger_accounts`, `journal_entries`, `enquiries`.
- Alembic head: `0006_enquiries`. Full chain: `0001_initial → 0002_inhouse_auth → 0003_passengers → 0004_approval_ttl → 0005_invoices_ledger → 0006_enquiries`.
- `build_journal_entry` enforces debit == credit in code.
- `StoragePassengerResolver` is tenant-isolated via composite unique indexes on `(tenant_id, email)` and `(tenant_id, passport_number)`.
- `VOYAGENT_STORES=memory` env toggle still forces in-memory stores for dev/tests.

### Deployment
- Live at [voyagent.globusdemos.com](https://voyagent.globusdemos.com) on commit `8182e1a` (tip of `origin/main`).
- Ubuntu 22.04 host, nginx + certbot for TLS.
- systemd units: `voyagent-api.service` (uvicorn :8010), `voyagent-web.service` (next start :3011), `voyagent-marketing.service` (next start :3012). All three active.
- Native Postgres 16 and Redis on :6379.
- Nginx vhost routes `/` → marketing, `/app/` → web, `/api/` → api (prefix-stripped), plus a loopback :8081 listener the web app uses for server-side fetches.
- Alembic at head `0006_enquiries` in prod.

### Tests
- ~250 new tests this session across Python and TypeScript, for a `pytest --collect-only` total of **754**.
- 94 driver tests across `amadeus` / `bsp` / `tally` / `vfs` / `tbo` (client, parser, dispatch, XML builders, canonical mapping).
- 55 API tests (approvals, enquiries, storage round-trip).
- 56 service tests (main wiring, revocation, domain agents, prompts, tenant registry, browser runner queue / handlers / artifacts).
- 47 TypeScript package tests (`@voyagent/sdk` client / SSE / errors; `@voyagent/chat` components).
- Vitest configs added to `packages/sdk` and `packages/chat`.
- All eight previously xfailed bugs are closed: tool output schema + retry-once, Anthropic rate-limit / connection retry with `Retry-After`, `email_verified` gating, Amadeus JSON decode mapping, BSP India HAF airline allow-list, VFS MFA routing, approval TTL + status enum, cross-tenant approval guard.

## 2. Must fix (known bugs)

Seven gaps flagged this session. None block prod today but all need to clear before the next tag.

### 2.1 TBO `_parse_search_offers` truncates `CountryCode`
- **Where.** `drivers/tbo/` search-offer parser.
- **Impact.** Two-character hard slice drops any offer with a one-letter code; bare `except Exception` silently swallows the drop.
- **Fix.** Use the raw code; validate against the ISO-3166 alpha-2 set explicitly and raise `TransientError` on malformed rows instead of `except Exception: continue`.

### 2.2 TBO `Money` construction `except Exception`
- **Where.** same parser.
- **Impact.** Malformed currency payloads silently drop offers instead of surfacing a data error.
- **Fix.** Catch the specific `ValueError` / `InvalidOperation` from `Money` construction and map to `TransientError` with the currency preview.

### 2.3 Tally `create_invoice` auto-mints a tenant id
- **Where.** `drivers/tally/`.
- **Impact.** Missing `tenant_id` silently creates a tenant record instead of failing; tenant-isolation invariant is violated in principle.
- **Fix.** Make `tenant_id` required at the driver boundary; raise `PermanentError("tenant_id required")` when absent.

### 2.4 VFS `datetime.fromisoformat` accepts naive datetimes
- **Where.** `drivers/vfs/`.
- **Impact.** Naive datetimes are converted to UTC using the host timezone, so scheduled slots shift by the host offset.
- **Fix.** Reject naive datetimes explicitly; require `tzinfo` on every appointment payload.

### 2.5 SDK `streamSSE` ignores injected `fetchImpl`
- **Where.** `packages/sdk/src/...` streaming helper.
- **Failing test.** None today; the docstring oversells testability that isn't actually wired.
- **Fix.** Plumb `fetchImpl` through to the streaming path; add a vitest that asserts the injected fetch is called.

### 2.6 Approvals `payload` / `resolved_by_user_id` always empty
- **Where.** `/api/approvals` response shape.
- **Impact.** UI shows blank payload and resolver identity columns; documented in README but still surfaces as dead fields.
- **Fix.** Add the two columns to `pending_approvals` in the next migration and thread them through the resolver.

### 2.7 Accounting / orchestrator test regressions from RBAC short-circuit
- **Where.** `tests/agent_runtime/test_accounting_tools.py`, `tests/agent_runtime/test_orchestrator*.py`.
- **Impact.** Failing tests on `main`; production runtime unaffected because the RBAC-before-approval ordering is correct.
- **Fix.** Update the fixtures / expected events to reflect the new short-circuit ordering, or split the orchestrator assertion so the RBAC denial path is its own case.

## 3. Open product decisions

Five questions that still need an answer before the next shipped wave closes.

### 3.1 TBO sandbox credentials
**Context.** `drivers/tbo` has search + check_rate wired but book / cancel / read raise `CapabilityNotSupportedError` because we have no sandbox account.
**Recommendation.** Request TBO sandbox credentials immediately. This is the cheapest unblock on the whole hotels track and promotes the driver from partial to wired with about two days of work.

### 3.2 Second hotels vendor: parallel or sequential?
**Context.** TBO as the only hotels vendor proves nothing about the adapter pattern. Hotelbeds is the obvious second.
**Recommendation.** Sequential. Finish TBO through booking first, then scaffold Hotelbeds against the same `HotelSearchDriver` Protocol. Building both in parallel risks baking a TBO-shaped compromise into the contract before it is stressed.

### 3.3 Concurrent sign-in: multi-session or rotation?
**Context.** The refresh-token store allows multiple live refresh tokens per user (multi-session). A stricter alternative is single-device rotation where a new sign-in revokes all other refresh tokens.
**Recommendation.** Keep multi-session for v0. Agency staff work from desktop + mobile + web simultaneously; rotation would log people out constantly. Revisit when we add session-management UI in `apps/web`.

### 3.4 Real email delivery provider
**Context.** `POST /api/auth/send-verification-email` logs the link to stdout and prod runs with `VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION=true`. Password reset and any later notification email flow will need the same provider.
**Recommendation.** Pick Postmark for the first wave. Single transactional-email use case, simple API, EU + US regions, no SES-style AWS account entanglement. Keep a thin provider adapter so SES / SMTP can drop in later.

### 3.5 Password-reset flow scope
**Context.** Same token-in-Redis primitive as email verification, but the delivery channel blocks shipping.
**Recommendation.** Ship the token issue / consume endpoints now against the stdout-log stub, then flip to the real provider when 3.4 lands. Reuse the `/api/auth/send-verification-email` code path; do not invent a second token type.

## 4. Next waves

Tiered by whether the work depends on external credentials or third-party approvals. Each entry: size (S/M/L), dependencies, done-when.

### Tier A — do next, no external deps

#### A1. Close the seven known bugs from section 2
- **Size.** M.
- **Dependencies.** None.
- **Done-when.** All seven fixes land, the accounting / orchestrator regressions in 2.7 are green, and a migration adds the two missing approvals columns.

#### A2. Populate `@voyagent/core` with OpenAPI TS codegen
- **Size.** M.
- **Dependencies.** None. FastAPI already emits OpenAPI.
- **Done-when.** `packages/core` publishes generated TS types consumed by `@voyagent/sdk` and `@voyagent/web`; codegen runs in CI and diffs cleanly.

#### A3. Password-reset flow
- **Size.** S.
- **Dependencies.** 3.5 decision; delivery still on the stdout stub is acceptable for A3.
- **Done-when.** `POST /api/auth/request-password-reset` + `POST /api/auth/reset-password` land with a Redis token, and the sign-in UI links to the flow.

#### A4. User profile + tenant settings pages
- **Size.** M.
- **Dependencies.** A2 for generated types.
- **Done-when.** `/app/settings/profile` (name, email, password change) and `/app/settings/tenant` (display name, tenant-level flags) exist and round-trip through the API.

#### A5. Audit-log viewer
- **Size.** S.
- **Dependencies.** None; `audit_events` is already populated.
- **Done-when.** `/app/audit` lists events with actor / action / subject / timestamp, filterable by actor and by entity id.

#### A6. Wire invoice-draft flow from chat
- **Size.** M.
- **Dependencies.** None.
- **Done-when.** "Draft invoice for X" in chat produces a tool-call that writes a draft row to `invoices` and surfaces the id in the reply; approval-gated before final.

#### A7. Playwright E2E for approvals + enquiries
- **Size.** M.
- **Dependencies.** None.
- **Done-when.** `tests/e2e/` covers the approve / reject path end-to-end and the enquiry lifecycle including promote-to-chat and two-step cancel.

### Tier B — blocked on external deps

#### B1. TBO sandbox booking end-to-end
- **Size.** L.
- **Dependencies.** 3.1 (TBO sandbox credentials).
- **Done-when.** `drivers/tbo` promotes book / cancel / read from stub to partial, and `tests/live/` covers a full sandbox booking cycle.

#### B2. Amadeus production + `issue_ticket`
- **Size.** L.
- **Dependencies.** Amadeus enterprise agreement.
- **Done-when.** `drivers/amadeus` runs against production creds, and `tests/live/` covers at least fare search + PNR create + issue_ticket.

#### B3. Tally desktop bridge via Tauri
- **Size.** L.
- **Dependencies.** Tauri app shell functional enough to host the bridge; desktop build pipeline.
- **Done-when.** Tally driver can read and post a real ledger entry through the desktop app on a test tenant machine.

#### B4. VFS selector pack v0
- **Size.** M.
- **Dependencies.** At least one tenant-specific VFS selector set.
- **Done-when.** VFS driver can log in and submit one form end-to-end through the browser runner for one tenant.

#### B5. Hotelbeds as second hotels vendor
- **Size.** L.
- **Dependencies.** B1; Hotelbeds sandbox access.
- **Done-when.** Hotelbeds search returns canonical `HotelSearchResult`s alongside TBO without changes to `HotelSearchDriver`.

#### B6. Real email delivery provider
- **Size.** S.
- **Dependencies.** 3.4 decision.
- **Done-when.** Verification + password-reset emails send via the chosen provider; `VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION` is unset in prod.

### Tier C — later

#### C1. Reports data pipeline improvements
- **Size.** L.
- **Dependencies.** Tier B accounting integrations for realistic multi-currency data.
- **Done-when.** Multi-currency totals (FX normalised at report-time), trial balance endpoint, and general-ledger drilldown ship; aging buckets remain correct under mixed currencies.

#### C2. Durable workflow engine (Temporal or Hatchet)
- **Size.** L.
- **Dependencies.** A real long-running workflow that exceeds what SSE + resumable sessions can handle; see D11 in [docs/DECISIONS.md](./docs/DECISIONS.md).
- **Done-when.** One nominated workflow (likely visa submission or ticket issuance on slow GDS paths) is re-expressed as a durable workflow with a decision ADR attached.

## Docs added in wave 2

- [`docs/GETTING_STARTED.md`](./docs/GETTING_STARTED.md) — first-day agency onboarding walkthrough
- [`docs/DRIVERS.md`](./docs/DRIVERS.md) — per-driver setup index, with one page per driver under `docs/drivers/`
- [`tests/integration/README.md`](./tests/integration/README.md) — opt-in real-Postgres integration fixture + round-trip test
- [`tests/load/README.md`](./tests/load/README.md) and [`tests/load/scenarios.md`](./tests/load/scenarios.md) — Locust load-test scenarios and baselines
