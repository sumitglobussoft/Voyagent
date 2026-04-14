"use client";

/**
 * Top-level chat UI container.
 *
 * Responsibilities:
 *   - Ensure a session exists (create one via the SDK if the caller didn't).
 *   - Render the message transcript, any pending approval, and the composer.
 *   - Thread the `useAgentStream` state into those children.
 *
 * The component is client-only — it uses hooks and talks to the SDK over
 * fetch + SSE. Hosts render it from a Server Component via standard React
 * composition; Next.js handles the RSC boundary automatically because of
 * the `"use client"` pragma.
 */
import { useEffect, useState, type ReactElement } from "react";

import type { VoyagentClient } from "@voyagent/sdk";

import { ApprovalPrompt } from "./ApprovalPrompt.web.js";
import { ComposerBar } from "./ComposerBar.web.js";
import { MessageList } from "./MessageList.web.js";
import { useAgentStream } from "./useAgentStream.js";

export interface ChatWindowProps {
  client: VoyagentClient;
  /**
   * If provided, used directly. Otherwise a new session is created on mount
   * using `tenantId` and `actorId`.
   */
  sessionId?: string;
  tenantId: string;
  actorId: string;
}

export function ChatWindow(props: ChatWindowProps): ReactElement {
  const { client, tenantId, actorId } = props;
  const [sessionId, setSessionId] = useState<string | null>(
    props.sessionId && props.sessionId.length > 0 ? props.sessionId : null,
  );
  const [initError, setInitError] = useState<Error | null>(null);

  useEffect(() => {
    if (sessionId !== null) return;
    let cancelled = false;
    (async () => {
      try {
        const { session_id } = await client.createSession();
        if (!cancelled) setSessionId(session_id);
      } catch (err) {
        if (!cancelled) {
          setInitError(err instanceof Error ? err : new Error(String(err)));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [actorId, client, sessionId, tenantId]);

  if (initError) {
    return (
      <div
        role="alert"
        className="m-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700"
      >
        Failed to initialize chat session: {initError.message}
      </div>
    );
  }

  if (sessionId === null) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="m-4 text-sm text-neutral-500"
      >
        Starting session...
      </div>
    );
  }

  return <ChatBody client={client} sessionId={sessionId} />;
}

function ChatBody({
  client,
  sessionId,
}: {
  client: VoyagentClient;
  sessionId: string;
}): ReactElement {
  const stream = useAgentStream({ client, sessionId });

  const disabled = stream.isStreaming || stream.pendingApprovals.length > 0;
  const disabledReason = stream.isStreaming
    ? "Agent is responding..."
    : stream.pendingApprovals.length > 0
      ? "Resolve the pending approval first."
      : undefined;

  const headApproval = stream.pendingApprovals[0];

  return (
    <div className="flex h-full flex-col bg-white text-neutral-900">
      <MessageList messages={stream.messages} />
      {headApproval !== undefined ? (
        <ApprovalPrompt
          approval={headApproval}
          busy={stream.isStreaming}
          onRespond={stream.respondToApproval}
        />
      ) : null}
      {stream.error !== null ? (
        <div
          role="alert"
          className="mx-4 mb-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {stream.error.message}
        </div>
      ) : null}
      <ComposerBar
        disabled={disabled}
        disabledReason={disabledReason}
        onSubmit={async (text: string) => {
          await stream.send(text);
        }}
      />
    </div>
  );
}
