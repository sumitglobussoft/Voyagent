# voyagent-api

FastAPI HTTP + SSE entry point for the Voyagent agentic travel OS.

## Run (dev)

```bash
uv sync
uv run voyagent-api
```

Serves on `http://localhost:8000`.

## Endpoints

- `GET /health` — liveness probe; returns `{"status": "ok"}`.
- `GET /schemas/money` — returns the JSON Schema for the canonical `Money`
  model. Smoke-tests the Pydantic canonical-model workspace import.
- `GET /openapi.json` — full OpenAPI document, auto-mounted by FastAPI.
  Consumed by `pnpm codegen` to regenerate `@voyagent/core` TS types.
- `GET /docs` — Swagger UI (dev).

## Status

Skeleton. Real routes land alongside the first vertical slice.
