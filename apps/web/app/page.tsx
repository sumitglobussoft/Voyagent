// Landing page. The chat surface itself lives under `/chat`; this page keeps
// a lightweight landing + link so the root isn't jarring for first-time
// visitors. Constructed as a Server Component — `ChatHost` is the client
// boundary that owns the `VoyagentClient`.

import Link from "next/link";

const apiUrl = process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

export default function Page() {
  return (
    <main style={{ padding: 32, fontFamily: "system-ui, sans-serif" }}>
      <h1>Voyagent — the Agentic Travel OS</h1>
      <p>
        API URL: <code>{apiUrl}</code>
      </p>
      <p>
        <Link href="/chat">Open the chat workspace →</Link>
      </p>
    </main>
  );
}
