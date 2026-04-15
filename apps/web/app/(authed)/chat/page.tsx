/**
 * Chat workspace page.
 *
 * Server component. `requireUser()` redirects to the sign-in page if there
 * is no valid session. The access token is read from cookies and handed
 * down to the client `<ChatHost>` so the SDK can sign requests.
 *
 * URL conventions (coordinated with the sidebar shell):
 *   - `/chat?session_id=<uuid>` opens an existing session in-place
 *   - `/chat?new=1` forces a brand-new session even if a `session_id` is
 *     also present (sidebar's "New chat" button hits this)
 */
import { cookies } from "next/headers";

import { ChatHost } from "@/components/ChatHost";
import { ACCESS_COOKIE, requireUser } from "@/lib/auth";

const apiUrl =
  process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

interface ChatPageProps {
  searchParams?: Promise<{ session_id?: string; new?: string }>;
}

export default async function ChatPage({ searchParams }: ChatPageProps) {
  const user = await requireUser();
  const jar = await cookies();
  const accessToken = jar.get(ACCESS_COOKIE)?.value ?? "";

  const params = (await searchParams) ?? {};
  const forceNew = params.new === "1" || params.new === "true";
  const sessionId = forceNew ? undefined : params.session_id;

  return (
    <div style={{ flex: 1, height: "100dvh", display: "flex", flexDirection: "column" }}>
      <ChatHost
        apiUrl={apiUrl}
        user={user}
        accessToken={accessToken}
        sessionId={sessionId}
        forceNew={forceNew}
      />
    </div>
  );
}
