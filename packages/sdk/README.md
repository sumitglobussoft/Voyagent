# @voyagent/sdk

Typed HTTP + SSE client for the Voyagent FastAPI backend.

This package is the **only** supported way for TypeScript clients (Web,
Desktop, Mobile) to call the Voyagent API. All request shapes, error types,
auth/tenancy injection, and retry policy live here — in one place — so every
surface talks to the backend the same way.

## Install

Workspace-linked from the monorepo root:

```json
"dependencies": {
  "@voyagent/sdk": "workspace:*",
  "@voyagent/core": "workspace:*"
}
```

## Usage — health + schemas

```ts
import { VoyagentClient, VoyagentApiError } from "@voyagent/sdk";

const client = new VoyagentClient({
  baseUrl: process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000",
  // tenantId: "acme-travel",
  // authToken: async () => (await session.getAccessToken()) ?? "",
});

try {
  const { status } = await client.health();
  console.log(status); // "ok"

  const schema = await client.moneySchema();
  console.log(schema);
} catch (err) {
  if (err instanceof VoyagentApiError) {
    console.error(err.status, err.method, err.path, err.responseBodyPreview);
  }
}
```

## Usage — chat

```ts
import { VoyagentClient, type AgentEvent } from "@voyagent/sdk";

const client = new VoyagentClient({ baseUrl: "http://localhost:8000" });

const { session_id } = await client.createSession({
  tenant_id: "demo-tenant",
  actor_id: "demo-actor",
});

for await (const event of client.sendMessage(session_id, {
  message: "Find me a flight to Goa next Friday",
})) {
  handle(event); // one AgentEvent per yield
}

// Human-in-the-loop: resume after an approval prompt by sending an empty
// message with the decisions dict.
for await (const event of client.sendMessage(session_id, {
  message: "",
  approvals: { "approval-123": true },
})) {
  handle(event);
}
```

`AgentEvent` is a discriminated union on `kind`:
`text_delta | tool_use | tool_result | approval_request | approval_granted
| approval_denied | error | final`. The stream closes after the `final` event
(or an `error` event) — the async iterator resolves cleanly.

Heartbeat SSE frames are filtered out for you; you only see real
`AgentEvent` payloads.

## Endpoints available today

- `health(): Promise<{ status: "ok" }>` — `GET /health`.
- `moneySchema(): Promise<Record<string, unknown>>` — `GET /schemas/money`.
- `createSession(input): Promise<{ session_id }>` — `POST /chat/sessions`.
- `getSession(id): Promise<SessionSummary>` — `GET /chat/sessions/{id}`.
- `sendMessage(id, input): AsyncIterable<AgentEvent>` — SSE from
  `POST /chat/sessions/{id}/messages`.

## Raw SSE

```ts
import { streamSSE } from "@voyagent/sdk";

for await (const ev of streamSSE<{ token: string }>("/some/other/stream")) {
  process.stdout.write(ev.data.token);
}
```

## Local development

```
NEXT_PUBLIC_VOYAGENT_API_URL=http://localhost:8000
```

Start the API with `make api` (or the equivalent in your environment). When
the backing `voyagent_agent_runtime` package isn't installed, the API returns
HTTP 503 with `{"detail": "agent_runtime_unavailable"}` for `/chat/*`; that
surfaces here as a `VoyagentApiError` with `status === 503`.

## Rules

- No Node-only APIs — must run in browser, Node 20+, and React Native.
- No hand-written `any`.
- ESM only.
