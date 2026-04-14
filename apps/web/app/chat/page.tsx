// Chat workspace page.
//
// Server Component. Reads the API URL from env and hands it to a client
// boundary (`ChatHost`) that constructs the `VoyagentClient` and renders
// `<ChatWindow>` from `@voyagent/chat`.
//
// TODO(auth): tenantId + actorId are hard-coded demo strings. Once the auth
// service lands this page should resolve them from the session cookie and
// forward a JWT to the client via a token provider — see the SDK's
// `authToken` option.

import { ChatHost } from "@/components/ChatHost";

const apiUrl =
  process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

export default function ChatPage() {
  return (
    <main style={{ height: "100dvh", display: "flex", flexDirection: "column" }}>
      <ChatHost apiUrl={apiUrl} tenantId="demo-tenant" actorId="demo-actor" />
    </main>
  );
}
