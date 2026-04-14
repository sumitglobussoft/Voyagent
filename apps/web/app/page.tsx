// Minimal page that proves the workspace wiring: importing from `@voyagent/sdk`
// forces type resolution across the monorepo to succeed at build time. Real UI
// (Tailwind, Tamagui on native, the chat surface) lands later.

import { VoyagentClient } from "@voyagent/sdk";

const apiUrl = process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

// Instantiate once at module scope. We don't hit the API during render in v0 —
// once we have real auth + tenancy this will move into an RSC with `await
// client.health()`.
const _client = new VoyagentClient({ baseUrl: apiUrl });
void _client;

export default function Page() {
  return (
    <main style={{ padding: 32, fontFamily: "system-ui, sans-serif" }}>
      <h1>Voyagent — the Agentic Travel OS</h1>
      <p>
        Planning phase. SDK wired, API URL: <code>{apiUrl}</code>
      </p>
    </main>
  );
}
