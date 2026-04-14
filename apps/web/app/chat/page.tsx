/**
 * Chat workspace page.
 *
 * Server component. `requireUser()` redirects to the sign-in page if there
 * is no valid session. The access token is read from cookies and handed
 * down to the client `<ChatHost>` so the SDK can sign requests.
 */
import { cookies } from "next/headers";

import { ChatHost } from "@/components/ChatHost";
import { ACCESS_COOKIE, requireUser } from "@/lib/auth";

const apiUrl =
  process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

export default async function ChatPage() {
  const user = await requireUser();
  const jar = await cookies();
  const accessToken = jar.get(ACCESS_COOKIE)?.value ?? "";

  return (
    <main style={{ height: "calc(100dvh - 56px)", display: "flex", flexDirection: "column" }}>
      <ChatHost apiUrl={apiUrl} user={user} accessToken={accessToken} />
    </main>
  );
}
