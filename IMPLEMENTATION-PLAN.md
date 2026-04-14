# Voyagent Implementation Plan

Living punch-list for the v0 alpha. Pairs with [README.md](./README.md) (what exists) and [docs/DECISIONS.md](./docs/DECISIONS.md) (why).

## 1. Shipped

What is in main today, grouped by area.

### Auth (in-house)
- `POST /api/auth/sign-up`, `/sign-in`, `/refresh`, `/sign-out`, `GET /api/auth/me`.
- Argon2id password hashing; HS256 access JWT (1h TTL); opaque refresh token (30d, single-use rotation).
- Redis-backed JWT revocation via jti denylist.
- `users` + `auth_refresh_tokens` tables; fixtures updated for password_hash.

### Chat + agent runtime
- `POST /chat/sessions`, `GET /chat/sessions`, `POST /chat/sessions/{id}/messages` (SSE stream).
- Real Anthropic client with prompt caching.
- In-process orchestrator in `services/agent_runtime/src/voyagent_agent_runtime/orchestrator.py`, streaming events to clients over FastAPI SSE.
- Approval-gated tool calls through `tools.py` + `_agent_loop.py`.
- Domain agents: `ticketing_visa`, `accounting`, `hotels_holidays` (new this session).

### Reports
- `GET /reports/receivables`, `/reports/payables`, `/reports/itinerary`, all tenant-isolated.
- Receivables and payables return empty-shape placeholders until an invoice driver lands.
- Itinerary reads from the session store.

### Hotels
- Canonical types: `HotelRoom`, `HotelRate`, `HotelProperty`, `HotelSearchResult`, `BoardBasis` enum in `schemas/canonical/travel.py`.
- `drivers/tbo/` with HTTP wiring for search + check_rate; book/cancel/read raise `CapabilityNotSupportedError`.

### Drivers
- `drivers/_contracts/` capability Protocols + error types are complete.
- `drivers/amadeus` partial (self-service sandbox), `drivers/tbo` partial (search/check_rate), `drivers/tally` / `drivers/bsp_india` / `drivers/vfs` at skeleton stage.

### Storage
- Tables: `users`, `tenants`, `sessions`, `messages`, `pending_approvals`, `tenant_credentials`, `audit_events`, `auth_refresh_tokens`, `passengers`.
- Alembic head: `0003_passengers`.
- `StoragePassengerResolver` replaces the old `NotImplementedError`; tenant isolation via composite unique indexes `(tenant_id, email)` and `(tenant_id, passport_number)`.
- `VOYAGENT_STORES=memory` env toggle still forces in-memory stores for dev/tests.

### Deployment
- Live at [voyagent.globusdemos.com](https://voyagent.globusdemos.com).
- Ubuntu 22.04 host, nginx + certbot for TLS.
- systemd units: `voyagent-api.service` (uvicorn :8010), `voyagent-web.service` (next start :3011), `voyagent-marketing.service` (next start :3012).
- Native Postgres 16 (`/etc/postgresql/16/main/`) and Redis on :6379.
- Nginx vhost routes `/` to marketing, `/app/` to web, `/api/` to api (prefix-stripped), plus a loopback :8081 listener for the web app's server-side fetches.
- Server env at `/opt/voyagent/.env.prod`; shared master Postgres credentials at `/etc/voyagent/postgres-master.env`.
- Python deps via `uv`, Node via nvm (v24) + pnpm via corepack. No Docker in the request path.

### Tests
- `tests/api/`: auth happy path + `test_auth_errors.py`, chat, reports.
- `tests/agent_runtime/`: orchestrator, tools, domain agents, approvals, passenger resolver (pg), plus new `test_orchestrator_errors.py`, `test_approvals.py`, `test_hotels_holidays.py`.
- `tests/drivers/{amadeus,bsp_india,tally,vfs,tbo}/`: per-driver happy path + `test_errors.py` additions.
- `tests/canonical/`: schema invariants + new `test_hotel.py`.
- `tests/storage/test_models.py`: fixtures updated for password_hash.
- `tests/e2e/` + `tests/live/`: Playwright and live probes rewritten to test the in-house auth gating contract.

## 2. Known bugs (must fix before next release)

Eight issues currently marked xfail. Each must go green before the next tag.

| # | Bug | Marked by | Impact | Fix sketch |
|---|---|---|---|---|
| 1 | Tool output not schema-validated; no retry-once policy | `tests/agent_runtime/test_tools.py` (xfail) | Malformed tool output propagates to the agent and corrupts downstream turns. | Validate each tool result against `ToolSpec.output_schema` in `tools.py`; on failure, retry the call once with a repair hint, then raise. |
| 2 | Anthropic `RateLimitError` not retried | `tests/agent_runtime/test_orchestrator_errors.py` | First 429 from Anthropic surfaces as a 500 to the chat stream. | Wrap the Anthropic call in `anthropic_client.py` with bounded exponential backoff on `RateLimitError` and `APIStatusError(5xx)`. |
| 3 | `email_verified` flag exists but sign-in doesn't gate on it | `tests/api/test_auth_errors.py` | Unverified emails can log in and obtain tokens. | Add the check in the sign-in handler in `services/api/.../auth.py`; return 403 with an `email_unverified` code. |
| 4 | Amadeus `json.JSONDecodeError` on 2xx body propagates raw | `tests/drivers/amadeus/test_errors.py` | Non-JSON 200 from Amadeus crashes the driver instead of raising a typed error. | Catch `JSONDecodeError` in the Amadeus client and raise `TransientError` with the body preview. |
| 5 | BSP India HAF parser accepts unknown airline codes | `tests/drivers/bsp_india/test_errors.py` | Unknown airline codes silently reconcile as valid. | Validate carrier codes against the shipped IATA set before accepting a HAF row. |
| 6 | VFS MFA signal routed to `AuthenticationError` | `tests/drivers/vfs/test_errors.py` | Tenants see "bad password" when MFA is actually required. | Detect the MFA selector in the VFS driver and raise `PermanentError("mfa_required")` instead. |
| 7 | `InMemorySessionStore` has no approval TTL / expiry state | `tests/agent_runtime/test_approvals.py` | Pending approvals never expire in dev/tests. | Add a TTL field + sweeper on approval records; mirror the contract the Postgres store will enforce. |
| 8 | `resolve_approval` doesn't check actor tenant | `tests/agent_runtime/test_approvals.py` | Cross-tenant approval resolution is possible in principle. | Require `tenant_id` on the resolve call and assert equality with the approval's tenant before mutating. |

## 3. Open product decisions

Five questions that block the next shipped wave. Each has my recommendation.

### 3.1 TBO sandbox credentials
**Context.** `drivers/tbo` has search and check_rate wired but book/cancel/read are stubbed as `CapabilityNotSupportedError` because we have no sandbox account. Without credentials we cannot integration-test the booking path or validate voucher issuance.
**Recommendation.** Request TBO sandbox credentials immediately. This is the cheapest unblock on the whole hotels track and promotes the driver from partial to wired with ~2 days of work.

### 3.2 Second hotels vendor: parallel or sequential?
**Context.** One-vendor hotels is a demo; two-vendor hotels is what proves the adapter pattern for the domain.
**Recommendation.** Sequential. Finish TBO through booking first, then scaffold Hotelbeds against the same `HotelSearchDriver` Protocol. Building both in parallel risks baking a TBO-shaped compromise into the contract before it's stressed.

### 3.3 Concurrent sign-in: multi-session or rotation?
**Context.** Today the refresh token store allows multiple live refresh tokens per user (multi-session). A stricter alternative is single-device rotation where a new sign-in revokes all existing refresh tokens.
**Recommendation.** Keep multi-session for v0. Travel agency staff work from desktop + mobile + web simultaneously; rotation would log people out constantly. Revisit when we add session-management UI in `apps/web`.

### 3.4 Approval TTL policy
**Context.** Bug #7 forces a decision: global TTL, per-tool TTL, or none. Today there is no TTL at all.
**Recommendation.** Per-tool TTL with a sensible global default (say 30 minutes). Irreversible tools (issue_ticket, post_journal_entry) should expire faster than read-only ones; the existing `ToolSpec` already has the hook for this.

### 3.5 `ToolSpec.output_schema` enforcement
**Context.** Bug #1 asks whether tool outputs should be runtime-validated. Today validation is honor-system.
**Recommendation.** Enforce at runtime with retry-once. The cost is a handful of Pydantic validations per turn; the benefit is that malformed tool output never poisons the conversation memory. This is the foundation for every later agent reliability investment.

## 4. Next waves

Prioritized roadmap. Do not start Wave N+1 until Wave N's done-when is met.

### Wave 1 — Reliability foundation
**Title.** Fix the eight xfailed bugs and resolve the five open product decisions.
**Effort.** M.
**Dependencies.** None.
**Done-when.** Zero xfails in `tests/`; IMPLEMENTATION-PLAN section 3 is collapsed to "resolved"; a short ADR lands for each decision in `docs/DECISIONS.md`.

### Wave 2 — Real vendor integrations
**Title.** TBO sandbox booking end-to-end and Amadeus production credentials.
**Effort.** L.
**Dependencies.** Wave 1; TBO sandbox creds delivered (decision 3.1); Amadeus enterprise agreement.
**Done-when.** `drivers/tbo` promotes book/cancel/read from stub to partial with a passing integration test against the sandbox; `drivers/amadeus` runs against production with at least fare search + PNR create covered by `tests/live/`.

### Wave 3 — Desktop and second vendor
**Title.** Tally desktop bridge, VFS selector pack, Hotelbeds second vendor.
**Effort.** L.
**Dependencies.** Wave 2; Tauri app shell functional enough to host the Tally bridge; at least one tenant-specific VFS selector set.
**Done-when.** Tally driver can read and post a real ledger entry from the desktop app; VFS driver can log in and submit one form end-to-end; Hotelbeds search returns canonical `HotelSearchResult`s alongside TBO.

### Wave 4 — Reports data pipeline
**Title.** Real invoices and ledger tables; receivables/payables wired to real data.
**Effort.** M.
**Dependencies.** Wave 3 (Tally posting path proves the ledger contract).
**Done-when.** New `invoices` and `ledger_entries` tables with Alembic migration; `/reports/receivables` and `/reports/payables` return tenant-real rows instead of empty shape; aging buckets computed server-side.

### Wave 5 — Lifecycle and UX completeness
**Title.** Passenger enquiry lifecycle, approvals UI, finance override board.
**Effort.** L.
**Dependencies.** Waves 1–4.
**Done-when.** An enquiry can be created, quoted, booked, delivered, and closed without leaving the chat; the web app exposes a full approvals queue with RBAC; accountants have an override board for reconciliation exceptions with a full audit trail.
