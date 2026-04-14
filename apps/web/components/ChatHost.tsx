"use client";

/**
 * Client boundary that owns the `VoyagentClient` instance.
 *
 * We can't construct a class instance inside a Server Component and hand it
 * to `<ChatWindow>` as a prop — RSC serialization requires plain JSON.
 * Instead the surrounding server page passes the plain `apiUrl` string, and
 * this client component builds the client once (memoized) and renders the
 * chat window.
 */
import { useMemo, type ReactElement } from "react";

import { ChatWindow } from "@voyagent/chat";
import { VoyagentClient } from "@voyagent/sdk";

export interface ChatHostProps {
  apiUrl: string;
  tenantId: string;
  actorId: string;
}

export function ChatHost({
  apiUrl,
  tenantId,
  actorId,
}: ChatHostProps): ReactElement {
  const client = useMemo(() => new VoyagentClient({ baseUrl: apiUrl }), [apiUrl]);
  return (
    <ChatWindow client={client} tenantId={tenantId} actorId={actorId} />
  );
}
