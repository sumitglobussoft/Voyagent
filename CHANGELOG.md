# Changelog

What's been shipped, in reverse chronological order. Mirror of the public page at
[voyagent.globusdemos.com/changelog](https://voyagent.globusdemos.com/changelog).

Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Voyagent is in v0; we don't ship semver-tagged releases yet — each entry is a
deploy to the demo host.

---

## 2026-04-15 — Wave 2: platform, polish, operations (6 parallel agents, ~200 new tests)

Six disjoint agent packs shipped in parallel, ~200 new unit + functional tests on top of the wave-1 98.

**Web experience polish:**
- Dark mode (Tailwind `darkMode: "class"`, ThemeProvider + cookie + localStorage + `prefers-color-scheme`)
- Toast notifications with server-action cookie-queue bridge
- 404 + 500 pages (public, authed, marketing variants)
- Dynamic favicons via Next 15 `app/icon.tsx`
- `AppProviders` shell wiring Theme / Locale / Toast / CommandPalette in a fixed nesting order

**i18n + command palette + API docs:**
- Hand-rolled i18n layer (no next-intl dep): `messages/{en,hi}.json` + `lib/i18n.ts` + `LocaleProvider` + `LocaleSwitcher`
- Real Hindi translations for the full UI string set
- `Cmd+K` / `Ctrl+K` command palette with fuzzy matcher, 8 hardcoded commands, accessible dialog
- `/docs/api` marketing page rendering the live OpenAPI JSON (1-hour ISR), linked from nav + sitemap
- `Intl`-based currency / date / relative-time helpers

**Product features:**
- `DELETE /api/chat/sessions/{id}` cascading to `pending_approvals` + `messages`
- `PATCH /api/chat/sessions/{id}` rename
- `GET /api/audit/export.csv` admin-only streaming export, 100k row cap
- Six new `/api/enquiries` filter params: `customer_email`, `destination`, `origin`, `depart_from`, `depart_to`, `created_from`, `created_to`
- Migration `0011_approvals_payload`: `payload JSONB` + `resolved_by_user_id` FK
- Session list item hover actions for rename / delete
- 64 new tests across chat, audit, enquiries, approvals, storage

**Agent runtime enhancements:**
- Per-tenant settings: model override, `system_prompt_suffix`, `rate_limit_per_minute/hour`, `daily_token_budget`, `locale`, `timezone`, `default_currency`
- Cost tracker writing to `session_costs` (Sonnet / Opus / Haiku 4.5 pricing), enforces daily budget as 429
- Sliding-window per-tenant rate limiter (process-local, async-locked)
- Tool result cache (allowlist: `search_flights`, `search_hotels`, `check_hotel_rate`, `list_ledger_accounts`, `lookup_passenger`; 5-min default TTL; tenant-scoped)
- `rehype-highlight` wired into the chat markdown pipeline with `github` / `github-dark` themes
- Migration `0012_tenant_settings_costs`
- `GET` / `PATCH /api/tenant-settings` (admin-only)

**Release infrastructure:**
- `.github/workflows/desktop-release.yml` — Tauri build matrix (macOS/Linux/Windows), PR dry-run job, release asset upload
- `.github/workflows/mobile-release.yml` — EAS build + OTA update, `workflow_dispatch` inputs
- `apps/mobile/eas.json` with development/preview/production profiles
- Passport OCR scaffold: real `parseMrz` (ICAO 9303 TD-3) + stubbed `extractPassport` + `PassportScanner` component using `expo-camera`
- `vitest` added to `apps/mobile` with a Node-env config, 19 OCR tests (check digits, ICAO specimen, generated vectors, error paths)

**Testing depth + documentation:**
- `tests/e2e/specs/a11y.spec.ts` using `@axe-core/playwright` across 19 pages
- `tests/integration/` with opt-in real-Postgres fixture (skipped by default)
- `tests/load/` with locust scenarios
- `docs/GETTING_STARTED.md` agency onboarding walkthrough
- `docs/DRIVERS.md` + `docs/drivers/{AMADEUS,TBO,TALLY,BSP_INDIA,VFS}.md` per-driver setup pages

**Off-site backups + staging + secret rotation:**
- `pg-backup-offsite.sh` rclone wrapper supporting AWS S3 / B2 / R2 / Wasabi / MinIO / DO Spaces
- `pg-restore.sh` with interactive confirmation gate
- Second systemd timer (03:30 UTC) + opt-in `.env.offsite-backup`
- `infra/deploy/staging/` bootstrap script + systemd unit templates + nginx vhost template (ports +10)
- `rotate-secret.sh` for JWT / DB / Redis / metrics / KMS
- `verify-secrets.sh` pre-deploy sanity check
- `docs/BACKUPS.md`, `docs/STAGING.md`, `docs/SECRET_ROTATION.md`

Commits `54e7598` → prod.

## 2026-04-15 — Wave 1: team onboarding, DevOps, observability, mobile polish, auth hardening, agent-to-ledger loop (5 + 1 agents, ~100 new tests)

- Tenant invites + roles + RBAC + migration `0008_invites`
- `PATCH /api/auth/profile`, password reset flow, profile + tenant settings pages
- GitHub Actions CI workflow (Python + TypeScript + Playwright + marketing build)
- `pg-backup.sh` + systemd timer (daily 02:00 UTC, 30-day retention) + `docs/RUNBOOK.md`
- Sentry API + web + marketing integration + PII scrubbing + tenant tagging middleware
- Prometheus `/internal/metrics` endpoint gated localhost-or-token
- Mobile sidebar drawer, `MobileHeader`, `Skeleton` primitive, enquiries responsive filter, 4 `loading.tsx` files
- Password strength validator + 58-entry blocklist
- TOTP 2FA (`pyotp`) with `/auth/totp/{setup,verify,disable}` + `/auth/sign-in-totp`
- API keys table + `vy_<prefix>_<body>` format, SHA256 hash storage, scopes + expiry + revoke + last_used
- Migration `0010_totp_and_api_keys`
- `draft_invoice` tool (approval-gated, auto-numbering per tenant, Decimal-only, mixed-currency error codes)
- `/reports/trial-balance` endpoint (as_of + include_zero)
- `tools/seed_demo.py` demo tenant seeder (idempotent, 5 enquiries + 3 invoices + 3 bills + 5 accounts + 3 balanced journals + 5 audit events)

Commits `c439755` → `5ae5b03` → prod.

## 2026-04-15 — Vendor onboarding doc

- New client-facing onboarding doc at `/docs/VENDOR_ONBOARDING` (also
  in `docs/VENDOR_ONBOARDING.md`) — per-vendor (TBO, Amadeus, Tally,
  VFS, Hotelbeds) sign-up links, account requirements, what to send
  back, security notes, suggested sequence
- Commit `5e48322`

## 2026-04-15 — Tier A polish

- External_id UUID drift audit: confirmed `external_id` is opaque (legacy
  IDP id, plain `String(128)`, never validated as `EntityId`); two other
  `uuid4()` calls (jti, verification token) are also opaque nonces. Comment-only
  documenting change
- Audit `kind` badge color map: `approval.granted` green, `.rejected` red,
  `.expired` grey, `auth.verify` amber, `tool.*` neutral. Identifier-aware
  formatting (no capitalize, monospace) for dotted/underscored kinds
- E2E tightened + new `redirect-safety.spec.ts`: 8 hostile-shape tests
  (`//evil.com`, `https://evil.com`, `javascript:alert(1)` × sign-in/sign-up)
  all confirmed reject + fall back to `/chat`. Final suite **161 passed
  / 0 failed / 3 skipped**
- Commit `b994465`

## 2026-04-15 — Three production bugs closed

- **`/app` redirect loop** — host nginx had `location = /app { return 308
  /app/; }` which looped against Next 15's `trailingSlash:false`
  normalization. Replaced with a straight `proxy_pass`. Source-of-truth in
  `infra/deploy/nginx-host/voyagent.globusdemos.com.conf` now matches live
- **Middleware drops `next=` on unauth redirects** — three layers were
  broken: the matcher `/app/:path*` was a no-op against Next 15's basePath
  stripping, the `pathname.startsWith('/app')` check fired on `/approvals`
  too (substring trap), and `req.url` carried the upstream
  `http://127.0.0.1:3011` because `next start -H 127.0.0.1` runs behind
  nginx. Rewrote middleware to normalize stripped/unstripped paths,
  reconstruct origin from `X-Forwarded-Host`, and add `safeNextPath()`
  validator (rejects `//evil.com`, `https://`, `javascript:`)
- **`/api/contact` 404 (not 429 as previously suspected)** — nginx
  `location /api/` was shadowing the marketing Next.js handler. Added
  `location = /api/contact` route ahead of the catch-all. Added a real
  per-IP / per-email / global sliding-window rate limiter
- Commits `0600f04` → `903ed6f`

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
