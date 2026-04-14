"use client";

/**
 * Client boundary that owns the `VoyagentClient` instance.
 *
 * Server-rendered parent passes a snapshot of the current access token plus
 * the resolved user so we never need to call back into the auth API from
 * the client. When the token expires mid-session the SDK call will 401 and
 * surface as an in-chat error — for v0 the user reloads to refresh.
 */
import { useMemo, type ReactElement } from "react";

import { ChatWindow } from "@voyagent/chat";
import { VoyagentClient } from "@voyagent/sdk";

// We redeclare the user shape here rather than importing from `@/lib/auth`
// because that module is `server-only` and would refuse to bundle into a
// client component.
export type ChatUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tenant_id: string;
  tenant_name: string;
  created_at: string;
};

export interface ChatHostProps {
  apiUrl: string;
  accessToken: string;
  user: ChatUser;
}

export function ChatHost({ apiUrl, accessToken, user }: ChatHostProps): ReactElement {
  const client = useMemo(
    () =>
      new VoyagentClient({
        baseUrl: apiUrl,
        authToken: (): Promise<string> => Promise.resolve(accessToken),
      }),
    [apiUrl, accessToken],
  );

  return (
    <ChatWindow
      client={client}
      tenantId={user.tenant_id}
      actorId={user.id}
    />
  );
}
