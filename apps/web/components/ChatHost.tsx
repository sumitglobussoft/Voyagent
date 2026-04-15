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
  /** Optional session id from `?session_id=...`. */
  sessionId?: string;
  /** True when `?new=1` was passed — forces a fresh session. */
  forceNew?: boolean;
}

export function ChatHost({
  apiUrl,
  accessToken,
  user,
  sessionId,
  forceNew,
}: ChatHostProps): ReactElement {
  // Nginx routes /api/* to FastAPI (stripping the prefix). The SDK's paths
  // are bare (`/chat/sessions`), so the consumer hands it the /api-prefixed
  // base. See deployment_runbook.md.
  const sdkBaseUrl = apiUrl.replace(/\/+$/, "") + "/api";
  const client = useMemo(
    () =>
      new VoyagentClient({
        baseUrl: sdkBaseUrl,
        authToken: (): Promise<string> => Promise.resolve(accessToken),
      }),
    [sdkBaseUrl, accessToken],
  );

  return (
    <ChatWindow
      client={client}
      sessionId={sessionId}
      forceNew={forceNew}
      tenantId={user.tenant_id}
      actorId={user.id}
    />
  );
}
