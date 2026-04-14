# Voyagent

**The Agentic Travel OS.**
*One chat. Every GDS, every accounting system, every workflow.*

## What this is

Voyagent is an agentic operating system for travel agencies. It replaces the manual, repetitive, multi-tool workflows that agency staff perform every day — ticketing, visa processing, hotel and holiday packaging, accounting, BSP reconciliation, GST/TDS compliance — with a chat interface backed by domain agents that actually execute the work through per-vendor drivers. The first market is India (BSP India, GST, TDS, UPI, Tally dominance, DPDP Act), but the architecture is globalization-safe from day one: currency, tax, statutory filings, identity documents, payment rails, and data residency are all abstracted. See [docs/DECISIONS.md](./docs/DECISIONS.md) (D8) for the rationale.

## Status

v0 alpha, live at [voyagent.globusdemos.com](https://voyagent.globusdemos.com) as of 2026-04-14. In-house auth, chat sessions with the streaming agent loop, the approvals queue, the enquiry lifecycle, receivables/payables/itinerary reports, and hotels search + rate-check through TBO all work end to end against a real Anthropic backend. Hotels booking, Amadeus ticketing, the Tally desktop bridge, and VFS browser automation are wired at the Protocol level but blocked on real vendor credentials. `pytest --collect-only` reports ~750 tests across Python and TypeScript suites.

## Architecture at a glance

| Layer          | Choice                                                                                |
| -------------- | ------------------------------------------------------------------------------------- |
| Frontends      | Next.js 15 web app (chat + approvals + enquiries), Next.js marketing site, Tauri 2 desktop (skeleton), Expo mobile (skeleton) |
| Backend        | Python 3.12, FastAPI, Pydantic v2, Anthropic SDK with prompt caching                  |
| Agent runtime  | In-process orchestrator + domain agents in `services/agent_runtime`, streamed to clients over FastAPI SSE. No external workflow engine. |
| Data           | Postgres 16 (SQLAlchemy 2 async + Alembic), Redis 7 for JWT revocation + email-verification tokens |
| Auth           | In-house: Argon2id passwords, HS256 access JWTs, opaque rotating refresh tokens, stub email verification |
| Shipped surfaces | Chat, approvals inbox, enquiry lifecycle, receivables / payables / itinerary reports |
| Build          | pnpm workspaces + uv workspace in a single monorepo                                   |

Deeper references live in [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md), [docs/STACK.md](./docs/STACK.md), and [docs/DECISIONS.md](./docs/DECISIONS.md) — in particular D9 (tech stack) and D11 (in-process agent runtime). Two deliberate removals from the earlier plan still stand: the Clerk-hosted auth path was replaced with the in-house stack above, and there is no external workflow engine in v0 — long-running tool calls run inside the same agent loop that streams to the client.

The canonical domain model lives in `schemas/canonical/` (Pydantic v2) and is the single shape every agent, tool, and driver speaks. Drivers live under `drivers/` and each declares a capability manifest — the orchestrator picks drivers per tenant at runtime based on what they can actually do, and degrades gracefully when a capability is missing.

## Repo layout

```
voyagent/
├── apps/
│   ├── web/                       Next.js 15 application
│   │   ├── app/approvals/         Pending + history approvals inbox
│   │   ├── app/enquiries/         Enquiry list, detail, new, promote-to-chat
│   │   ├── app/chat/              Chat session UI
│   │   └── lib/api.ts             Server-side fetch helper (cookie-forwarding)
│   ├── marketing/                 Next.js marketing site
│   ├── desktop/                   Tauri 2 shell (skeleton)
│   └── mobile/                    Expo app (skeleton)
├── packages/
│   ├── core/                      Shared TS types + canonical model mirror
│   ├── chat/                      Chat UI primitives (vitest)
│   ├── ui/                        Design-system components
│   ├── sdk/                       Typed API client (vitest)
│   ├── config/                    Shared ESLint/tsconfig/tailwind
│   └── icons/                     Icon set
├── services/
│   ├── api/                       FastAPI app (auth, chat, reports, approvals, enquiries, health)
│   ├── agent_runtime/             Orchestrator, domain agents, tool runtime, SSE events
│   ├── browser_runner/            Playwright worker for portals without APIs
│   └── worker/                    Background worker slot (unused in v0)
├── drivers/
│   ├── _contracts/                Capability Protocols + CapabilityManifest + error types
│   ├── amadeus/                   Amadeus self-service sandbox driver (partial)
│   ├── tbo/                       TBO hotels driver (search + check_rate wired)
│   ├── tally/                     Tally XML-over-HTTP driver (skeleton)
│   ├── bsp_india/                 BSPlink HAF parser (skeleton)
│   └── vfs/                       VFS Global browser-automation driver (skeleton)
├── schemas/
│   ├── canonical/                 Pydantic v2 canonical domain model
│   └── storage/                   SQLAlchemy 2 ORM models
│       ├── invoice.py             Invoices table (AR)
│       ├── ledger.py              Ledger accounts + journal entries
│       ├── enquiry.py             Enquiries + lifecycle enum
│       └── passenger.py           Passengers (tenant-isolated)
├── tests/                         pytest suites
└── infra/
    ├── alembic/                   Migrations (head: 0006_enquiries)
    ├── deploy/                    Host setup + systemd units + nginx vhost
    └── scripts/                   Operational helpers
```

## Running locally

Backend:

```
uv sync --package voyagent-api
uv run uvicorn voyagent_api.main:app --reload --port 8010
```

Frontend:

```
pnpm install
pnpm -r --filter "./packages/*" build
pnpm --filter @voyagent/web build
pnpm --filter @voyagent/marketing build
```

Tests:

```
uv run pytest tests/
pnpm --filter @voyagent/sdk test
pnpm --filter @voyagent/chat test
pnpm test
```

For tests and dev work that shouldn't touch Postgres, set `VOYAGENT_STORES=memory` to force the in-memory store implementations. Otherwise, point `VOYAGENT_DB_URL` at a local Postgres and run migrations with `uv run alembic -c infra/alembic/alembic.ini upgrade head` (the current head is `0006_enquiries`). Redis is required in both modes for JWT revocation and for email-verification token storage; run `redis-server` on the default port or set `VOYAGENT_REDIS_URL`.

The web app expects the API to be reachable at `VOYAGENT_INTERNAL_API_URL` for its server-side fetches; in local dev this is usually `http://127.0.0.1:8010`.

## Deployment

Voyagent runs on a single Ubuntu 22.04 host. Nginx + certbot terminate TLS, and the three application processes (`voyagent-api`, `voyagent-web`, `voyagent-marketing`) run as systemd units against native Postgres 16 and Redis 7. There is no container in the request path. The production database is at migration head `0006_enquiries`, which covers the six migrations `0001_initial → 0002_inhouse_auth → 0003_passengers → 0004_approval_ttl → 0005_invoices_ledger → 0006_enquiries`. See [`infra/deploy/README.md`](./infra/deploy/README.md) for the host-setup runbook and systemd unit reference.

## Key environment variables

| Variable                                         | Purpose                                                                     |
| ------------------------------------------------ | --------------------------------------------------------------------------- |
| `VOYAGENT_DB_URL`                                | SQLAlchemy async Postgres URL.                                              |
| `VOYAGENT_STORES`                                | `memory` forces in-memory stores for dev/tests; omit in prod.               |
| `VOYAGENT_REDIS_URL`                             | Redis URL for JWT revocation denylist, refresh rotation, email tokens.      |
| `VOYAGENT_AUTH_SECRET`                           | HS256 signing secret for access JWTs. Must be set in prod.                  |
| `VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION`          | `true` to bypass the verified-email gate on sign-in (prod today).           |
| `VOYAGENT_AUTH_VERIFICATION_TTL_SECONDS`         | Lifetime of the email-verification token in Redis. Default 24h.             |
| `VOYAGENT_INTERNAL_API_URL`                      | Loopback URL the web app uses for server-side fetches (e.g. `http://127.0.0.1:8081`). |
| `VOYAGENT_AGENT_MODEL`                           | Overrides the Anthropic model id for the orchestrator.                      |
| `ANTHROPIC_API_KEY`                              | Anthropic credential for the agent loop.                                    |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET`    | Amadeus self-service sandbox.                                               |
| `VOYAGENT_TBO_USERNAME` / `VOYAGENT_TBO_PASSWORD`| TBO hotels driver (sandbox creds pending).                                  |
| `BSP_INDIA_USERNAME` / `BSP_INDIA_PASSWORD`      | BSPlink portal credentials.                                                 |
| `VFS_USERNAME` / `VFS_PASSWORD`                  | VFS Global credentials used by the browser runner.                          |

## Domains

| Domain                | Status   | What it can do today                                                              |
| --------------------- | -------- | --------------------------------------------------------------------------------- |
| Chat + agent runtime  | Live     | Streaming Anthropic-backed orchestrator with prompt caching, per-session memory.  |
| Approvals             | Live     | Pending + history inbox at `/app/approvals`; `/api/approvals` list/get/resolve with lazy expiry sweep and cross-tenant 404. |
| Enquiries             | Live     | `/app/enquiries` CRUD + filter + search + two-step cancel + promote-to-chat session. |
| Reports               | Live     | `/reports/receivables` and `/reports/payables` with 0-30/31-60/61-90/90+ aging buckets served from `invoices` + `bills` + `journal_entries`; `/reports/itinerary` from session store. |
| `ticketing_visa`      | Partial  | Fare search intake, passenger resolution, approval-gated issue/cancel stubs.      |
| `hotels_holidays`     | Partial  | Hotel search and rate-check against TBO; book/cancel/read still stubbed.          |
| `accounting`          | Partial  | Receivables/payables read paths live; Tally posting path still a skeleton.        |

Cross-cutting tools: passenger resolver (real, storage-backed via `StoragePassengerResolver`, tenant-isolated on composite unique indexes), approval gate (Postgres-backed `pending_approvals` with TTL + enum status), and the reporter. Every side-effecting tool call is gated behind an explicit approval. Tools carry `side_effect` and `reversible` flags; irreversible actions (ticket issuance, payment, visa submission, journal posting) always pause for human confirmation and are recorded in the `audit_events` table.

## Drivers

| Driver              | Status              | Notes                                                            |
| ------------------- | ------------------- | ---------------------------------------------------------------- |
| `drivers/_contracts`| Complete            | All capability Protocols defined.                                |
| `drivers/amadeus`   | Partial             | Self-service sandbox only; production needs enterprise creds.    |
| `drivers/tbo`       | Partial             | Search + check_rate wired; book/cancel/read stubbed pending sandbox creds. |
| `drivers/tally`     | Skeleton            | XML-over-HTTP on :9000; desktop-bound; no read_invoice yet.      |
| `drivers/bsp_india` | Skeleton            | HAF parser with a 164-code IATA airline allow-list; HTTP fetch scaffolded only. |
| `drivers/vfs`       | Skeleton            | Thin wrapper over `services/browser_runner`; MFA-aware; selectors tenant-provided. |

## Testing

Python suites under `tests/` are organised as:

- `tests/agent_runtime/` — orchestrator, tools, domain agents, approvals, prompts, tenant registry
- `tests/api/` — auth, chat, reports, approvals, enquiries, storage round-trip
- `tests/drivers/{amadeus,bsp_india,tally,tbo,vfs}/` — client, parser, dispatch, XML builders, canonical mapping
- `tests/browser_runner/` — queue, handlers, artifacts
- `tests/canonical/` — schema invariants
- `tests/storage/` — ORM + fixtures
- `tests/services/` — service wiring
- `tests/e2e/` and `tests/live/` — Playwright against a running stack and probes against the deployed host

TypeScript suites live under `packages/*/tests` and run under Vitest (SDK client/SSE/errors and chat components are the two with real coverage today).

`uv run pytest --collect-only tests/` reports **754** tests.

## Open questions and roadmap

The full shipped history, known-bug punch-list, open product decisions, and the tiered roadmap live in [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md). Short version of what is currently open:

- Seven known bugs flagged this session — a TBO country-code truncation, TBO and Tally `except Exception` swallowing, a VFS naive-datetime conversion, an SDK `streamSSE` fetch-injection oversight, approvals' empty `payload` / `resolved_by_user_id` fields, and a batch of pre-existing accounting/orchestrator test regressions.
- Five open product decisions — TBO sandbox credentials, whether Hotelbeds lands parallel to TBO or after, concurrent-sign-in policy, the real email delivery provider, and the password-reset flow.
- Next-wave roadmap is split into three tiers by whether progress depends on external credentials or approvals.

## License

See [LICENSE](./LICENSE).
