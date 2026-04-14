# Voyagent

**The Agentic Travel OS.**
*One chat. Every GDS, every accounting system, every workflow.*

## What this is

Voyagent is an agentic operating system for travel agencies. It replaces the manual, repetitive, multi-tool workflows that agency staff perform every day — ticketing, visa processing, hotel and holiday packaging, accounting, BSP reconciliation, GST/TDS compliance — with a chat interface backed by domain agents that actually execute the work through per-vendor drivers. The first market is India (BSP India, GST, TDS, UPI, Tally dominance, DPDP Act), but the architecture is globalization-safe from day one: currency, tax, statutory filings, identity documents, payment rails, and data residency are all abstracted. See [docs/DECISIONS.md](./docs/DECISIONS.md) (D8) for the rationale.

## Status

v0 alpha, live at [voyagent.globusdemos.com](https://voyagent.globusdemos.com). In-house auth, chat sessions, and the streaming agent loop are working end to end against a real Anthropic backend. Reports and the hotels domain are scaffolded. Driver implementations are at the skeleton stage pending real vendor credentials — see the table below for what is wired today.

## Architecture at a glance

| Layer          | Choice                                                                                |
| -------------- | ------------------------------------------------------------------------------------- |
| Frontends      | Next.js 15 web app, Next.js marketing site, Tauri 2 desktop (skeleton), Expo mobile (skeleton) |
| Backend        | Python 3.12, FastAPI, Pydantic v2, Anthropic SDK with prompt caching                  |
| Agent runtime  | In-process orchestrator + domain agents in `services/agent_runtime`, streamed to clients over FastAPI SSE. No external workflow engine. |
| Data           | Postgres 16 (SQLAlchemy 2 async + Alembic), Redis 7 for JWT revocation + pub/sub      |
| Auth           | In-house: Argon2id passwords, HS256 access JWTs, opaque rotating refresh tokens       |
| Build          | pnpm workspaces + uv workspace in a single monorepo                                   |

Deeper references live in [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md), [docs/STACK.md](./docs/STACK.md), and [docs/DECISIONS.md](./docs/DECISIONS.md) — in particular D9 (tech stack) and D11 (in-process agent runtime). Note two deliberate removals from the earlier plan: Clerk has been replaced with in-house auth (Argon2id + HS256 JWT + rotating refresh tokens, Redis-backed revocation), and Temporal has been dropped from v0. Long-running tool calls run inside the same agent loop that streams to the client; durability will be re-evaluated when workflow latency exceeds what SSE + resumable sessions can handle.

The canonical domain model lives in `schemas/canonical/` (Pydantic v2) and is the single shape every agent, tool, and driver speaks. Drivers live under `drivers/` and each declares a capability manifest — the orchestrator picks drivers per tenant at runtime based on what they can actually do, and degrades gracefully when a capability is missing.

## Repo layout

```
voyagent/
├── apps/
│   ├── web/                 Next.js 15 application (chat UI, approvals, reports)
│   ├── marketing/           Next.js marketing site
│   ├── desktop/             Tauri 2 shell (skeleton)
│   └── mobile/              Expo app (skeleton)
├── packages/
│   ├── core/                Shared TS types + canonical model mirror
│   ├── chat/                Chat UI primitives
│   ├── ui/                  Design-system components
│   ├── sdk/                 Typed API client
│   ├── config/              Shared ESLint/tsconfig/tailwind
│   └── icons/               Icon set
├── services/
│   ├── api/                 FastAPI app (auth, chat, reports, approvals, health)
│   ├── agent_runtime/       Orchestrator, domain agents, tool runtime, SSE events
│   ├── browser_runner/      Playwright worker for portals without APIs
│   └── worker/              Background worker slot (unused in v0)
├── drivers/
│   ├── _contracts/          Capability Protocols + CapabilityManifest + error types
│   ├── amadeus/             Amadeus self-service sandbox driver (partial)
│   ├── tbo/                 TBO hotels driver (search + check_rate wired)
│   ├── tally/               Tally XML-over-HTTP driver (skeleton)
│   ├── bsp_india/           BSPlink HAF parser (skeleton)
│   └── vfs/                 VFS Global browser-automation driver (skeleton)
├── schemas/
│   ├── canonical/           Pydantic v2 canonical domain model
│   └── storage/             SQLAlchemy 2 ORM models
├── tests/                   pytest suites (api, agent_runtime, drivers, canonical, storage, e2e, live)
└── infra/
    ├── alembic/             Migrations (head: 0003_passengers)
    ├── deploy/              Host setup + systemd units + nginx vhost
    └── scripts/             Operational helpers
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

For tests and dev work that shouldn't touch Postgres, set `VOYAGENT_STORES=memory` to force the in-memory store implementations. Otherwise, point `VOYAGENT_DB_URL` at a local Postgres and run migrations with `uv run alembic -c infra/alembic/alembic.ini upgrade head` (the current head is `0003_passengers`). Redis is required in both modes for JWT revocation; run `redis-server` on the default port or set `VOYAGENT_REDIS_URL`.

The web app expects the API to be reachable at `VOYAGENT_INTERNAL_API_URL` for its server-side fetches; in local dev this is usually `http://127.0.0.1:8010`.

## Deployment

Voyagent runs on a single Ubuntu 22.04 host. Nginx + certbot terminate TLS, and the three application processes (`voyagent-api`, `voyagent-web`, `voyagent-marketing`) run as systemd units against native Postgres 16 and Redis 7. There is no Docker in the request path. See [`infra/deploy/README.md`](./infra/deploy/README.md) for the host-setup runbook and systemd unit reference.

## Key environment variables

| Variable                   | Purpose                                                                     |
| -------------------------- | --------------------------------------------------------------------------- |
| `VOYAGENT_DB_URL`          | SQLAlchemy async Postgres URL. Absence + `VOYAGENT_STORES=memory` = in-mem. |
| `VOYAGENT_REDIS_URL`       | Redis URL for JWT revocation denylist and refresh rotation bookkeeping.     |
| `VOYAGENT_AUTH_SECRET`     | HS256 signing secret for access JWTs. Must be set in prod.                  |
| `VOYAGENT_INTERNAL_API_URL`| Loopback URL the web app uses for server-side fetches (e.g. `http://127.0.0.1:8081`). |
| `ANTHROPIC_API_KEY`        | Anthropic credential for the agent loop.                                    |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | Amadeus self-service sandbox.                            |
| `TBO_USERNAME` / `TBO_PASSWORD` / `TBO_BASE_URL` | TBO hotels driver (sandbox creds pending).            |
| `BSP_INDIA_USERNAME` / `BSP_INDIA_PASSWORD`      | BSPlink portal credentials.                           |
| `VFS_USERNAME` / `VFS_PASSWORD`                  | VFS Global credentials used by the browser runner.    |

## Domains

| Domain agent       | What it can do today                                                              |
| ------------------ | --------------------------------------------------------------------------------- |
| `ticketing_visa`   | Fare search intake, passenger resolution, approval-gated issue/cancel stubs.      |
| `hotels_holidays`  | Hotel search and rate-check against TBO (book/cancel/read still stubbed).         |
| `accounting`       | Receivables/payables read paths; journal posting routed through Tally driver (skeleton). |

Cross-cutting tools: passenger resolver (real, storage-backed via `StoragePassengerResolver`, tenant-isolated on composite unique indexes), approval gate (in-memory in dev, Postgres-backed `pending_approvals` in prod), and the reporter (read-only `/reports/receivables`, `/reports/payables`, `/reports/itinerary`). Receivables and payables currently return empty shapes — they are waiting on the invoices/ledger tables planned in Wave 4 of the implementation plan.

Every side-effecting tool call is gated behind an explicit approval. Tools carry `side_effect` and `reversible` flags; irreversible actions (ticket issuance, payment, visa submission, journal posting) always pause for human confirmation and are recorded in the `audit_events` table.

## Drivers

| Driver              | Status              | Notes                                                            |
| ------------------- | ------------------- | ---------------------------------------------------------------- |
| `drivers/_contracts`| Complete            | All capability Protocols defined.                                |
| `drivers/amadeus`   | Skeleton + partial  | Self-service sandbox only; production needs enterprise creds.    |
| `drivers/tbo`       | Skeleton + partial  | Search + check_rate wired; book/cancel/read stubbed pending sandbox creds. |
| `drivers/tally`     | Skeleton            | XML-over-:9000; desktop-bound; no read_invoice yet.              |
| `drivers/bsp_india` | Skeleton            | Local HAF file parser; HTTP fetch scaffolded only.               |
| `drivers/vfs`       | Skeleton            | Thin wrapper over `services/browser_runner`; selectors tenant-provided. |

## Testing

```
uv run pytest tests/
pnpm test
```

`tests/` is split across `api/`, `agent_runtime/`, `drivers/<name>/`, `canonical/`, `storage/`, `e2e/` (Playwright against a running stack), and `live/` (probes against the deployed host). See [docs/TESTING.md](./docs/TESTING.md) for how the live and e2e suites are wired.

## Open questions and roadmap

Current punch-list, known bugs (xfailed), open product decisions, and the prioritized wave plan live in [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md). Short version:

- Fix the eight known-xfailed bugs in the agent loop, auth, and drivers.
- Answer the five open product decisions (TBO creds, second hotels vendor, concurrent sign-in, approval TTL, tool output schema validation).
- Graduate TBO hotel booking, promote Amadeus to production creds, and build the Tally desktop bridge.
- Land the invoices/ledger tables so receivables and payables return real data instead of empty shapes.

## License

See [LICENSE](./LICENSE).
