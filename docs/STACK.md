# Tech Stack & Repo Layout

> Concrete follow-up to [D9](./DECISIONS.md#d9--tech-stack-typescript-frontends--python-agentdriver-runtime). Read that decision first.

## Stack at a glance

| Layer | Pick | Notes |
|---|---|---|
| Monorepo (JS side) | **pnpm workspaces + Turborepo** | Fast, boring |
| Monorepo (Python side) | **uv workspace** | Single lockfile, fast installs |
| Web | **Next.js 15 (App Router)** | RSC + streaming for chat |
| Desktop shell | **Tauri 2** (Rust) | ~10 MB binary, plugin system |
| Desktop frontend | **Vite + React 19** | Simpler than Next.js inside Tauri |
| Mobile | **Expo + React Native (new arch)** | EAS for builds & OTA updates |
| Shared UI | **Tamagui** (cross-platform) + **Tailwind** (web-only bits) | |
| State | **Zustand** (client) + **TanStack Query** (server-state) | |
| Design primitives | **Radix** on web, Tamagui primitives on native | |
| API transport | **REST + SSE** (fetch/EventSource) | WebSocket only for desktop↔mobile relay |
| Backend HTTP | **FastAPI** | Native SSE, great OpenAPI |
| Canonical model | **Pydantic v2** | Single source of truth |
| TS contract | Pydantic → JSON Schema → **`openapi-typescript`** → `@voyagent/core` | Generated, checked into git |
| Agent loop | **Anthropic Python SDK** (prompt caching on) | |
| Browser automation | **Playwright (Python)** | Dedicated worker service |
| Workflows | **Temporal** (Python SDK) | Long-running, retryable, durable |
| DB | **PostgreSQL 16** + **SQLAlchemy 2 / SQLModel** | |
| Cache / queue | **Redis 7** | |
| Object store | **S3-compatible** (AWS S3 / R2 / MinIO for local dev) | |
| Auth | **Clerk** or **WorkOS** (web/mobile) + Tauri-native token exchange for desktop | TBD — not blocking |
| Telemetry | **OpenTelemetry** → Grafana/Tempo/Loki | Traces include agent turns |
| CI | **GitHub Actions** | `pnpm test` + `uv run pytest` + Turbo cache |

## Repo layout

```
voyagent/
├── README.md
├── LICENSE
├── .gitignore
├── pnpm-workspace.yaml
├── turbo.json
├── package.json
├── pyproject.toml                 # uv workspace root
├── uv.lock
│
├── apps/
│   ├── web/                       # Next.js 15 — @voyagent/web
│   ├── desktop/                   # Tauri 2 shell + Vite/React — @voyagent/desktop
│   │   ├── src-tauri/             # Rust shell, plugins
│   │   └── src/                   # Vite + React frontend
│   └── mobile/                    # Expo — @voyagent/mobile
│
├── packages/
│   ├── core/                      # @voyagent/core — generated TS types + runtime adapters
│   ├── sdk/                       # @voyagent/sdk — thin HTTP + SSE client
│   ├── ui/                        # @voyagent/ui — Tamagui + Tailwind components
│   ├── chat/                      # @voyagent/chat — agentic chat UI (shared across 3 clients)
│   ├── config/                    # @voyagent/config — eslint, tsconfig, tailwind, tamagui presets
│   └── icons/                     # @voyagent/icons — shared icon set
│
├── services/
│   ├── api/                       # FastAPI public HTTP + SSE — voyagent-api
│   ├── agent_runtime/             # Orchestrator, domain agents, tool runtime — voyagent-agent-runtime
│   ├── worker/                    # Temporal workers — voyagent-worker
│   └── browser_runner/            # Playwright worker for portal drivers — voyagent-browser-runner
│
├── drivers/
│   ├── _contracts/                # Pydantic capability interfaces + manifest schema
│   ├── amadeus/                   # FareSearchDriver, PNRDriver (Amadeus)
│   ├── tally/                     # AccountingDriver (Tally, XML-over-HTTP + ODBC sidecar)
│   ├── bsp_india/                 # BSPDriver (IATA India)
│   ├── upi/                       # PaymentDriver (UPI)
│   ├── vfs/                       # VisaPortalDriver (browser automation)
│   └── ...                        # one folder per external system
│
├── schemas/
│   └── canonical/                 # Pydantic v2 models — the canonical domain model
│       ├── money.py
│       ├── tax.py
│       ├── passenger.py
│       ├── itinerary.py
│       ├── booking.py
│       ├── invoice.py
│       ├── journal.py
│       └── ...
│
├── infra/
│   ├── docker/                    # Compose files for local dev (pg, redis, temporal, minio)
│   ├── terraform/                 # Cloud infra (later)
│   └── scripts/                   # codegen, lint, release
│
├── docs/
│   ├── ACTIVITIES.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   └── STACK.md                   # this file
│
└── .github/
    └── workflows/
```

### Why separate `services/` and `drivers/`

- **`services/`** are long-running processes (API, agent runtime, workers, browser runner). They import drivers.
- **`drivers/`** are Python packages — one per external system — installed as workspace members. They depend only on `_contracts/` and `schemas/canonical/`, never on each other or on services. This keeps the adapter layer clean (per [D2](./DECISIONS.md#d2--vendor-agnostic-across-gds-and-accounting)).

### Why desktop uses Vite + React, not Next.js

Next.js App Router assumes a server and is awkward inside a Tauri shell (RSC, route handlers, and SSR don't translate). Vite + React is the ergonomic pattern. All shared pieces live in `packages/ui`, `packages/chat`, `packages/sdk`, and `packages/core`, so desktop and web look and behave identically — the shell around them differs.

## The Pydantic → TS contract flow

This is load-bearing. If it breaks, vendor-agnosticism breaks.

```
schemas/canonical/*.py            (Pydantic v2 — source of truth)
        │
        ├─► services/api exposes OpenAPI at /openapi.json
        │
        │   infra/scripts/codegen.ts:
        │     openapi-typescript ./openapi.json -o packages/core/src/generated.ts
        │
        └─► packages/core/src/generated.ts   (checked into git, CI-verified fresh)
                │
                ├─► @voyagent/sdk (typed HTTP + SSE client)
                ├─► @voyagent/chat (typed tool-call UI)
                └─► apps/{web,desktop,mobile}
```

CI gate: regenerate `generated.ts` on every push and fail if the working tree is dirty. That guarantees the contract never drifts.

## Local dev loop (target)

```bash
# Once
pnpm install                         # JS deps
uv sync                              # Python deps
docker compose -f infra/docker/dev.yml up -d   # pg, redis, temporal, minio

# Day to day
pnpm dev                             # turbo runs web + desktop + mobile dev servers
uv run voyagent-api                  # FastAPI with reload
uv run voyagent-agent-runtime        # agent loop with reload
uv run voyagent-worker               # Temporal worker
uv run voyagent-browser-runner       # Playwright worker

# Contract
pnpm codegen                         # regenerate TS types from FastAPI OpenAPI
```

## Package naming convention

- JS packages: `@voyagent/<name>` (e.g., `@voyagent/core`, `@voyagent/ui`).
- Python packages: `voyagent_<name>` distribution name, `voyagent.<name>` import path (e.g., `voyagent.drivers.tally`, `voyagent.schemas.canonical`).
- Services: `voyagent-<name>` binary / script entry (e.g., `voyagent-api`, `voyagent-worker`).

## Not chosen (on purpose)

- **tRPC** — conflicts with FastAPI. We get type-safety via Pydantic → OpenAPI → TS instead.
- **GraphQL** — overkill for an internal contract between our own clients and our own API.
- **Monorepo in one language** — we need TS for tri-platform UI and Python for integrations; neither alone is strong enough in the other domain.
- **Electron** — rejected in [D9](./DECISIONS.md#d9--tech-stack-typescript-frontends--python-agentdriver-runtime).
- **Django** — fine framework, but FastAPI's native SSE + OpenAPI + Pydantic v2 story beats it for an agent-streaming API.
- **Prisma / Drizzle on the backend** — SQLAlchemy 2 + SQLModel keeps the ORM in Python with Pydantic models.

## Open stack questions (non-blocking)

- **Auth provider.** Clerk vs WorkOS vs Ory. Decide when we scaffold the first protected route.
- **Workflow engine.** Temporal is the pick; revisit if ops complexity outweighs durability benefits after the first vertical slice.
- **Design-system boundary.** Tamagui for everything vs. Tamagui on native + Radix/Tailwind on web. Decide during `packages/ui` scaffolding.
- **Hosted vs self-hosted Temporal.** Temporal Cloud vs a local cluster; cost-dependent.

## First executable step (when we're ready to leave planning)

Scaffold the skeleton: root `pnpm-workspace.yaml`, `turbo.json`, `package.json`, `pyproject.toml` with empty workspace members, plus placeholder `apps/web`, `services/api`, `schemas/canonical`. That gives us a repo that `pnpm install && uv sync` can bootstrap before any real code is written.
