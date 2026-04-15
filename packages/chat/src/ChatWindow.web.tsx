"use client";

/**
 * Top-level chat UI container.
 *
 * Responsibilities:
 *   - Ensure a session exists (create one via the SDK if the caller didn't).
 *   - Render the session header, transcript, pending approvals, and composer.
 *   - Surface Stop-generating while a turn is streaming.
 *   - Offer an empty-state with example prompts on a brand-new session.
 *
 * Client-only — uses hooks and talks to the SDK over fetch + SSE. Hosts
 * render it from a Server Component via standard React composition;
 * Next.js handles the RSC boundary automatically because of `"use client"`.
 */
import { useEffect, useState, type ReactElement } from "react";

import type { VoyagentClient } from "@voyagent/sdk";

import { ApprovalPrompt } from "./ApprovalPrompt.web.js";
import { ComposerBar } from "./ComposerBar.web.js";
import { EmptyState } from "./EmptyState.web.js";
import { MessageList } from "./MessageList.web.js";
import { SessionHeader } from "./SessionHeader.web.js";
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
  /**
   * When true, ignore `sessionId` and always mint a fresh session. Mirrors
   * the `/chat?new=1` URL convention used by the web shell.
   */
  forceNew?: boolean;
}

export function ChatWindow(props: ChatWindowProps): ReactElement {
  const { client, tenantId, actorId, forceNew } = props;
  const [sessionId, setSessionId] = useState<string | null>(
    !forceNew && props.sessionId && props.sessionId.length > 0
      ? props.sessionId
      : null,
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
  const [seedText, setSeedText] = useState<string>("");
  const [title, setTitle] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState<string | null>(null);

  // Pull session metadata once on mount for the header strip. We
  // deliberately skip re-fetching on every message — the title is
  // generated server-side on the first message, so we poll after the
  // first turn completes instead.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const summary = await client.getSession(sessionId);
        if (cancelled) return;
        setTitle(summary.title ?? null);
        // `created_at` isn't on SessionSummary; fall back to "now" if the
        // SDK ever starts returning it.
        const anySummary = summary as unknown as { created_at?: string };
        if (anySummary.created_at) setCreatedAt(anySummary.created_at);
      } catch {
        /* swallow — header gracefully renders "New chat". */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, sessionId]);

  // After the first turn finishes streaming, refresh the session once so
  // the header picks up the newly-generated title.
  useEffect(() => {
    if (stream.isStreaming) return;
    if (title !== null) return;
    if (stream.messages.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const summary = await client.getSession(sessionId);
        if (!cancelled && summary.title) setTitle(summary.title);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, sessionId, stream.isStreaming, stream.messages.length, title]);

  const disabled = stream.isStreaming || stream.pendingApprovals.length > 0;
  const disabledReason = stream.isStreaming
    ? "Agent is responding..."
    : stream.pendingApprovals.length > 0
      ? "Resolve the pending approval first."
      : undefined;

  const headApproval = stream.pendingApprovals[0];
  const isEmpty = stream.messages.length === 0 && !stream.isStreaming;

  return (
    <div className="flex h-full flex-col bg-neutral-50 text-neutral-900">
      <SessionHeader title={title} createdAt={createdAt} />
      {isEmpty ? (
        <EmptyState onPick={(s) => setSeedText(s)} />
      ) : (
        <MessageList
          messages={stream.messages}
          isStreaming={stream.isStreaming}
          onRegenerate={stream.regenerate}
        />
      )}
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
      {stream.isStreaming ? (
        <div className="flex justify-center px-4 pb-2">
          <button
            type="button"
            onClick={() => stream.stop()}
            className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100"
            data-testid="stop-generating"
          >
            Stop generating
          </button>
        </div>
      ) : null}
      <ComposerBar
        disabled={disabled}
        disabledReason={disabledReason}
        seedText={seedText}
        onSubmit={async (text: string) => {
          setSeedText("");
          await stream.send(text);
        }}
      />
    </div>
  );
}
