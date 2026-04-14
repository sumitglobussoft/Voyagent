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

## Usage

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
  } else {
    throw err;
  }
}
```

## Endpoints available today

- `health(): Promise<{ status: "ok" }>` — `GET /health`.
- `moneySchema(): Promise<Record<string, unknown>>` — `GET /schemas/money`.

More endpoints will be added here as the API grows — always typed, always
exported from this package.

## Streaming (future)

```ts
import { streamSSE } from "@voyagent/sdk";

for await (const ev of streamSSE<{ token: string }>("/agent/stream")) {
  process.stdout.write(ev.data.token);
}
```

> No server endpoint currently emits SSE. `streamSSE` is scaffolding for when
> the agent runtime lands.

## Local development

Point the client at your local FastAPI dev server:

```
NEXT_PUBLIC_VOYAGENT_API_URL=http://localhost:8000
```

Start the API with `make api` (or the equivalent in your environment).

## Rules

- No Node-only APIs — must run in browser, Node 20+, and React Native.
- No hand-written `any`.
- ESM only.
