// Chat workspace page.
//
// Server Component. Checks the Clerk session + organisation server-side;
// if either is missing we redirect to sign-in rather than render an empty
// chat surface. The chat UI itself lives behind a client boundary
// (`ChatHost`) that constructs the `VoyagentClient` and handles token
// refresh through `useAuth().getToken`.

import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { ChatHost } from "@/components/ChatHost";

const apiUrl =
  process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000";

export default async function ChatPage() {
  const session = await auth();

  // No session → hand off to Clerk's sign-in flow. Middleware already
  // enforces this; the redirect here is defence-in-depth in case the
  // middleware matcher is edited later.
  if (!session.userId) {
    redirect("/sign-in");
  }

  // Voyagent is multi-tenant by design: an authenticated user without an
  // active Clerk organisation has no tenant to scope the workspace to.
  // Send them to sign-in so Clerk can walk them through org selection.
  if (!session.orgId) {
    redirect("/sign-in");
  }

  return (
    <main style={{ height: "calc(100dvh - 56px)", display: "flex", flexDirection: "column" }}>
      <ChatHost apiUrl={apiUrl} />
    </main>
  );
}
