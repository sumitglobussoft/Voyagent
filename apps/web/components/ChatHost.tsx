"use client";

/**
 * Client boundary that owns the `VoyagentClient` instance.
 *
 * We can't construct a class instance inside a Server Component and hand it
 * to `<ChatWindow>` as a prop — RSC serialization requires plain JSON.
 * Instead the surrounding server page passes the plain `apiUrl` string, and
 * this client component builds the client once (memoized) and renders the
 * chat window.
 *
 * Auth: the SDK is configured with an async `authToken` getter that pulls
 * a fresh Clerk session JWT on every request. Clerk's tokens are short
 * lived (roughly 60 s) so we never cache them locally — the getter lets
 * the SDK re-read on each call.
 *
 * The `tenantId` / `actorId` props on `<ChatWindow>` are vestigial —
 * the API now derives both from the JWT and ignores the request body.
 * Until `@voyagent/chat` drops those required props we thread Clerk's
 * `orgId` / `userId` through purely to satisfy the type; nothing on the
 * server trusts them.
 *
 * TODO(voyagent-chat): update `@voyagent/chat` to read the session from
 * the API response rather than from caller-supplied props, then drop
 * these from this component.
 */
import { useMemo, type ReactElement } from "react";

import { useAuth } from "@clerk/nextjs";
import { ChatWindow } from "@voyagent/chat";
import { VoyagentClient } from "@voyagent/sdk";

export interface ChatHostProps {
  apiUrl: string;
}

export function ChatHost({ apiUrl }: ChatHostProps): ReactElement {
  const { getToken, orgId, userId } = useAuth();

  const client = useMemo(
    () =>
      new VoyagentClient({
        baseUrl: apiUrl,
        authToken: async (): Promise<string> => {
          const token = await getToken();
          if (!token) {
            // The page-level server guard should prevent this, but a
            // defensive throw gives a clear error in the client console
            // rather than surfacing as a silent 401 from the API.
            throw new Error(
              "Voyagent: no Clerk session token available — user is signed out.",
            );
          }
          return token;
        },
      }),
    [apiUrl, getToken],
  );

  // Vestigial props — see module docstring. The API ignores these.
  return (
    <ChatWindow
      client={client}
      tenantId={orgId ?? "unknown-tenant"}
      actorId={userId ?? "unknown-actor"}
    />
  );
}
