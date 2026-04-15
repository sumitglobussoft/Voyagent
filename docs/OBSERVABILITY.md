# Observability

Minimal ops visibility for voyagent. This doc is the source of truth for what
error tracking / metrics we ship today, and what we still need.

## In scope today

- **Sentry** errors + transactions for:
  - `services/api` (FastAPI, via `sentry-sdk[fastapi]`)
  - `apps/web` (Next.js 15, via `@sentry/nextjs`)
  - `apps/marketing` (Next.js 15, via `@sentry/nextjs`)
- **Prometheus** metrics at `GET /internal/metrics` on the API (gated).
- **Tenant tagging** on every API request so Sentry issues can be filtered
  per-tenant in the UI.

## Env vars

Every DSN is optional. When the DSN is blank the corresponding SDK init is a
silent no-op — the app boots and runs normally, no crashes, no warnings.

### API (`services/api`)

| Var | Default | Notes |
|-----|---------|-------|
| `VOYAGENT_SENTRY_DSN_API` | _(unset)_ | Required to turn Sentry on |
| `VOYAGENT_SENTRY_ENVIRONMENT` | `production` | `development` / `staging` / `production` |
| `VOYAGENT_SENTRY_TRACES_SAMPLE_RATE` | `0.1` | 10% transaction sampling |
| `VOYAGENT_VERSION` | `0.0.0-dev` | Used as Sentry `release` and on `voyagent_api_build_info` |
| `VOYAGENT_GIT_SHA` | `unknown` | Stamped on `voyagent_api_build_info` |
| `VOYAGENT_METRICS_TOKEN` | _(unset)_ | Required to scrape `/internal/metrics` from non-localhost |

### Web (`apps/web`) and Marketing (`apps/marketing`)

| Var | Default | Notes |
|-----|---------|-------|
| `NEXT_PUBLIC_SENTRY_DSN` | _(unset)_ | Browser-side DSN (public) |
| `SENTRY_DSN` | falls back to `NEXT_PUBLIC_SENTRY_DSN` | Node + edge runtime DSN |
| `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | `production` | |
| `SENTRY_TRACES_SAMPLE_RATE` / `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` | `0.1` | |
| `SENTRY_ORG` | _(unset)_ | Build-time, source-map upload |
| `SENTRY_PROJECT_WEB` / `SENTRY_PROJECT_MARKETING` | _(unset)_ | Build-time |
| `SENTRY_AUTH_TOKEN` | _(unset)_ | Build-time, source-map upload only |
| `VOYAGENT_VERSION` | `0.0.0-dev` | Used as Sentry `release` |

## Viewing errors

1. Open the Sentry project for the service (`voyagent-api`, `voyagent-web`, or
   `voyagent-marketing`).
2. Filter by tag `tenant_id:<uuid>` to see only errors for a specific customer.
   The API middleware stamps `tenant_id` and `user_id` on every event.
3. For release-specific regressions, filter by `release:<VOYAGENT_VERSION>`.

## Scraping metrics

The `/internal/metrics` endpoint is not publicly exposed. It accepts requests
from `127.0.0.1` / `::1` unconditionally, and from anywhere else only if the
caller presents `X-Voyagent-Metrics-Token: <VOYAGENT_METRICS_TOKEN>`. All other
callers get a 404 (not a 401 — we don't advertise the endpoint to strangers).

Example from the deploy host (inside the compose network):

```sh
curl -s http://voyagent-api:8000/internal/metrics \
     -H "X-Voyagent-Metrics-Token: $VOYAGENT_METRICS_TOKEN"
```

Exposed series:

- `voyagent_api_requests_total{method,path,status}` — counter
- `voyagent_api_request_duration_seconds{method,path}` — histogram
- `voyagent_api_active_sessions` — gauge (see TODO below)
- `voyagent_api_build_info{version,commit}` — gauge, always `1`

Path labels are bucketed so numeric / UUID-ish segments collapse to `:id`.

## Suggested Sentry alerts

- **Issue alert — new error group**: trigger on "a new issue is created" in any
  of the three projects; route to on-call.
- **Issue alert — regression**: trigger when a resolved issue comes back;
  route to on-call.
- **Metric alert — API p95 latency**: `transaction.duration` p95 > 5s over 10
  min → warn; > 10s → page.
- **Metric alert — error rate**: `event.type:error` count > 20 over 5 min →
  page.

## What is NOT wired yet

- **Structured logging.** API still uses stdlib `logging` to stdout. TODO:
  adopt `structlog` or equivalent, ship JSON lines.
- **Log aggregation.** No Loki / CloudWatch / ELK yet — logs live in the
  container and vanish on restart. TODO: pick a sink.
- **Agent-runtime APM.** `services/agent_runtime` has no Sentry + no metrics;
  owned by a parallel workstream.
- **Desktop + mobile error tracking.** Skipped until Tauri / Expo builds run
  on real hardware.
- **`voyagent_api_active_sessions` gauge is a stub** that always reports `0`.
  Wiring the real count requires reaching into the agent runtime's session
  store, which is owned by a parallel agent. Upgrade this to a real query
  once that lands.
