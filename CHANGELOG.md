# Changelog

What's been shipped, in reverse chronological order. Mirror of the public page at
[voyagent.globusdemos.com/changelog](https://voyagent.globusdemos.com/changelog).

Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Voyagent is in v0; we don't ship semver-tagged releases yet — each entry is a
deploy to the demo host.

---

## 2026-04-15 — Marketing alignment + changelog + Playwright E2E

- Marketing pages (`/domains/*`, `/integrations`, `/architecture`, `/product`)
  rewritten to match what's actually live; aspirational vendor / status claims
  removed
- New `/changelog` page on the marketing site, wired into nav + footer + sitemap
- Playwright E2E suite for approvals + enquiries (25 tests across 5 specs +
  shared fixtures); tests run against the live deployment
- Commit `ac41dc5`

## 2026-04-15 — Demo account + chat path fixes

- Demo account `demo@voyagent.globusdemos.com` exposed on `/app/sign-in` with
  a "Use demo credentials" pre-fill link; tenant deliberately isolated
- Fixed SDK consumers (web/mobile/desktop) to pass `/api`-prefixed base URL so
  the browser-side SDK reaches FastAPI through nginx
- Fixed `createSession` to post an empty body — the API derives `tenant_id`
  and `actor_id` from the bearer JWT
- Commits `351fa9b`, `1b40920`, `4a370e9`, `4035e99`

## 2026-04-14 — Approvals inbox + enquiry lifecycle

- New `/api/approvals` and `/app/approvals` — list pending tool-call
  approvals, approve/reject from a finance inbox, 15-minute TTL, cross-tenant
  requests return 404 (no existence leak)
- New `enquiries` table + full CRUD: `/api/enquiries` and UI at
  `/app/enquiries` (list + filter + search + create + detail + edit +
  promote-to-chat)
- Status lifecycle `new → quoted → booked` with `cancelled` as a terminal
  state
- Migration `0006_enquiries`
- Commits `b194818`, `8182e1a`

## 2026-04-14 — Real-data reports

- `invoices`, `bills`, `ledger_accounts`, `journal_entries` tables added
  (migration `0005_invoices_ledger`)
- `build_journal_entry` helper enforces `debit == credit` invariant in code,
  not via DB triggers
- `/reports/receivables` and `/reports/payables` now query real data with
  0-30 / 31-60 / 61-90 / 90+ aging buckets

## 2026-04-14 — Eight bug fixes from the error-path test pass

- Tool output schema validation + retry-once on schema mismatch
- Anthropic `RateLimitError` / `APIConnectionError` retry with exponential
  backoff (`Retry-After` honored when present)
- Sign-in gates on `email_verified`; distinguishable 401 codes
  (`email_not_verified` vs `invalid_credentials`)
- Amadeus JSON decode errors mapped to typed driver errors (no raw exceptions
  through the boundary)
- BSP India HAF parser airline allow-list (164 IATA carriers) + regex
  pre-check
- VFS MFA / 2FA / OTP signals routed to `PermanentError` (was being
  miscategorized as auth failure)
- `pending_approvals.expires_at` + `status="expired"` enum value with lazy
  sweep
- `resolve_approval(actor_tenant_id)` cross-tenant guard
- Commit `178fcad`

## 2026-04-14 — Hotels domain

- New `hotels_holidays` agent with approval-gated booking
- New canonical hotel models: `HotelRoom`, `HotelRate`, `HotelProperty`,
  `HotelSearchResult`, `BoardBasis` enum
- New TBO driver — search + price re-check wired with real HTTP; booking
  stubbed pending sandbox credentials
- Migration `0003_passengers` + `StoragePassengerResolver` end-to-end
- Postgres session stores wired by default when `VOYAGENT_DB_URL` is set

## 2026-04-14 — In-house auth replaces Clerk everywhere

- Argon2id password hashing; HS256 JWT access tokens (1 hour) + opaque
  refresh tokens (30 days, single-use rotation)
- `httpOnly` cookies on web (`voyagent_at`), SecureStore on mobile/desktop
- Redis-backed JWT `jti` denylist for revocation
- Email verification flow stubbed (`/send-verification-email`,
  `/verify-email`); real delivery pending a provider decision
- Migration `0002_inhouse_auth`

## 2026-04-14 — Native deployment

- Migrated off Docker Compose to systemd-supervised processes
- Three units: `voyagent-api` (uvicorn :8010), `voyagent-web` (Next start
  :3011), `voyagent-marketing` (Next start :3012)
- Native Postgres 16 (shared host instance), native Redis 7
- Single host nginx + certbot for TLS
- Removed Clerk + Temporal + Docker from docs and configs

## Earlier — Foundations

- In-process agent loop with prompt caching (Anthropic SDK)
- Three domain agents: `ticketing_visa`, `accounting`, `hotels_holidays`
- Canonical Pydantic v2 data model: flights, hotels, visa, finance, lifecycle
- Five driver skeletons: Amadeus, TBO, Tally, BSP India, VFS — all conform to
  typed driver contracts
- Real-time chat with SSE streaming + approval-gated tool calls
- Multi-tenant isolation enforced at every storage query
- Tests: ~750 Python (pytest) + ~47 TypeScript (vitest)

---

For roadmap detail see [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md). For
architecture decisions see [docs/DECISIONS.md](docs/DECISIONS.md).
