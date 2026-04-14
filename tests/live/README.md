# voyagent-tests-live

Live HTTP integration tests for the deployed Voyagent stack. These
tests hit the real deployed URL, not stubs or mocks, and assert on the
HTTP contract: status classes, headers, content-types, JSON shape, and
the specific error strings the service emits.

They complement (do not replace) the stubbed contract tests in
`tests/api/`.

## Running

Against production (default target):

```
uv run --directory tests/live pytest
```

Or explicitly:

```
VOYAGENT_BASE_URL=https://voyagent.globusdemos.com \
  uv run --directory tests/live pytest
```

Against a local stack (for example an `ops up` dev loop):

```
VOYAGENT_BASE_URL=http://127.0.0.1:8480 \
  uv run --directory tests/live pytest
```

Shard the slower / longer tests:

```
uv run --directory tests/live pytest -m contract
uv run --directory tests/live pytest -m "not contract"
```

Parallel via `pytest-xdist`:

```
uv run --directory tests/live pytest -n auto
```

## Pre-flight

`conftest.py` runs a synchronous `GET /api/health` on session start.
If it is not 2xx (or the host is unreachable), the whole run aborts
with exit code 2 before any test collects. This surfaces the
reachability failure loud and fast instead of drowning it in 50
cascading assertion errors.

## Target resolution

- `VOYAGENT_BASE_URL` env var wins.
- Default: `https://voyagent.globusdemos.com`.
- Trailing slashes are stripped so routes always start with `/`.

## Endpoint matrix

| Concern | Endpoints |
| --- | --- |
| Health | `/api/health`, `/health` |
| Marketing | `/`, `/product`, `/features`, `/architecture`, `/integrations`, `/security`, `/pricing`, `/about`, `/contact` |
| Domains | `/domains/ticketing-visa`, `/domains/hotels-holidays`, `/domains/accounting` |
| Docs | `/docs/{ARCHITECTURE,DECISIONS,CANONICAL_MODEL,STACK,ACTIVITIES}` |
| Metadata | `/robots.txt`, `/sitemap.xml`, `/favicon.svg`, `/og-image.svg` |
| API contract | `/api/schemas/money`, `/api/openapi.json` |
| API chat | `/api/chat/sessions`, `/api/chat/sessions/{id}`, `/api/chat/sessions/{id}/messages` |
| CORS | `OPTIONS /api/health`, `OPTIONS /api/chat/sessions` |
| App (gated) | `/app`, `/app/dashboard` |
| Perf budget | `/`, `/api/health` |

## Error-contract stance

The chat routes currently return **401 / 403 / 503 / 307 / 308** when
hit unauthenticated, because `ANTHROPIC_API_KEY` and
`CLERK_SECRET_KEY` are placeholders in the deployed environment. All
five status codes are treated as legal. Once real credentials are
configured, `test_api_chat_unavailable.py` should be tightened to
assert a single specific auth-failure code and to add happy-path
tests.

Similarly, `/app` may currently return a 500 with "Clerk" in the body
until the Clerk keys are configured. That is the known state; the
test pins it and will fail loudly if *any other* 500 starts appearing.

## Known gaps

- No real Clerk sign-in flow; no authenticated chat turn.
- No WebSocket or streaming (`/api/chat/sessions/{id}/stream`) tests.
- No Cloudflare bypass; tests accept 304 on static assets.
- No multi-tenant cross-check.
- No load testing.
- No content-integrity checks against a snapshot of the marketing copy.
