# voyagent-api

FastAPI HTTP + SSE entry point for the Voyagent agentic travel OS.

## Run (dev)

```bash
uv sync
uv run voyagent-api
```

Serves on `http://localhost:8000`.

## Endpoints

### Core

- `GET /health` — liveness probe; returns `{"status": "ok"}`.
- `GET /schemas/money` — returns the JSON Schema for the canonical `Money`
  model. Smoke-tests the Pydantic canonical-model workspace import.
- `GET /openapi.json` — full OpenAPI document, auto-mounted by FastAPI.
  Consumed by `pnpm codegen` to regenerate `@voyagent/core` TS types.
- `GET /docs` — Swagger UI (dev).

### Chat (SSE)

Backed by the `voyagent_agent_runtime` Python package. If that package isn't
installed in the current environment, every `/chat/*` route returns HTTP 503
with body `{"detail": "agent_runtime_unavailable"}` — the rest of the API
continues to serve.

- `POST /chat/sessions` → create a session.

  ```json
  { "tenant_id": "demo-tenant", "actor_id": "demo-actor" }
  ```

  Response: `{ "session_id": "..." }` (HTTP 201).

- `GET /chat/sessions/{session_id}` → metadata (no message bodies).

  ```json
  {
    "session_id": "...",
    "tenant_id": "demo-tenant",
    "actor_id": "demo-actor",
    "message_count": 4,
    "pending_approvals": [{ "approval_id": "ap_1", "summary": "Book INR 12000 flight?" }]
  }
  ```

- `POST /chat/sessions/{session_id}/messages` → **SSE stream** of
  `AgentEvent` objects.

  Request body:

  ```json
  { "message": "Find me a flight to Goa next Friday", "approvals": null }
  ```

  Or, to resume a paused turn after an approval prompt:

  ```json
  { "message": "", "approvals": { "ap_1": true } }
  ```

  Response: `text/event-stream`. Frames:

  - `event: agent_event` / `data: <AgentEvent.model_dump(mode="json")>`
  - `event: heartbeat` / `data:` every 15 s while the turn is alive
  - Stream closes when a `final`-kind event arrives, the client disconnects,
    or the runtime raises (in which case one synthetic `error`-kind event is
    emitted before the close).

### `curl` example

```bash
# 1. Create a session.
SID=$(curl -s -X POST http://localhost:8000/chat/sessions \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"demo-tenant","actor_id":"demo-actor"}' \
  | jq -r .session_id)

# 2. Stream an agent turn.
curl -N -X POST "http://localhost:8000/chat/sessions/$SID/messages" \
  -H 'content-type: application/json' \
  -H 'accept: text/event-stream' \
  -d '{"message":"Find me a flight to Goa next Friday"}'
```

## CORS

`VOYAGENT_API_CORS_ORIGINS` — comma-separated list of allowed origins.
Defaults to `http://localhost:3000` for the Next.js dev server.

## Status

Chat surface is wired. The Python agent runtime it fronts (`voyagent_agent_runtime`)
is authored in a sibling service — if that package is absent the `/chat/*`
routes degrade to 503 by design.
