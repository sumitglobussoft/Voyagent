"use client";

/**
 * `useAgentStream` — the state machine behind the chat UI.
 *
 * One hook call per live chat session. It owns:
 *
 * * the visible message timeline (user + assistant messages),
 * * a queue of pending approvals (surfaced by the human-in-the-loop flow),
 * * the `isStreaming` flag that gates the composer input,
 * * a coarse `error` slot for the last SSE/API failure.
 *
 * The core job is **coalescing** the raw `AgentEvent` stream into the UI
 * model in `types.ts`. Text deltas for a given `turn_id` are concatenated
 * into a single assistant message; tool_use + tool_result pairs collapse
 * into a single `ToolCallEntry`; approval_request events pause the turn and
 * are resumed by calling `respondToApproval`.
 */
import { useCallback, useRef, useState } from "react";

import type {
  AgentEvent,
  VoyagentClient,
  VoyagentApiError,
} from "@voyagent/sdk";

import type { ApprovalRequest, ChatMessage, ToolCallEntry } from "./types.js";

export interface UseAgentStreamOptions {
  client: VoyagentClient;
  sessionId: string;
}

export interface UseAgentStreamResult {
  messages: ChatMessage[];
  pendingApprovals: ApprovalRequest[];
  isStreaming: boolean;
  error: VoyagentApiError | Error | null;
  /**
   * The most recently-seen SSE event id. Populated as events arrive so
   * the UI can surface "connection state" or persist it across reloads.
   * The SDK handles reconnection transparently; this is informational.
   */
  lastEventId: string | null;
  send: (text: string, approvals?: Record<string, boolean>) => Promise<void>;
  respondToApproval: (approvalId: string, granted: boolean) => Promise<void>;
}

function nowIso(): string {
  return new Date().toISOString();
}

function newId(): string {
  // crypto.randomUUID is available in modern browsers and Node 20+.
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `msg-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

/**
 * Apply a single `AgentEvent` to the rolling message list, returning a new
 * list. Kept as a pure function so the reducer semantics are easy to audit.
 */
function reduceEvent(
  messages: ChatMessage[],
  event: AgentEvent,
): ChatMessage[] {
  // Find (or synthesize) the assistant message for this turn_id.
  const idx = messages.findIndex(
    (m): m is Extract<ChatMessage, { kind: "assistant" }> =>
      m.kind === "assistant" && m.id === event.turn_id,
  );

  const ensureAssistant = (): {
    list: ChatMessage[];
    current: Extract<ChatMessage, { kind: "assistant" }>;
    index: number;
  } => {
    if (idx >= 0) {
      const current = messages[idx];
      if (current && current.kind === "assistant") {
        return { list: [...messages], current: { ...current }, index: idx };
      }
    }
    const fresh: Extract<ChatMessage, { kind: "assistant" }> = {
      kind: "assistant",
      id: event.turn_id,
      text: "",
      timestamp: event.timestamp,
      toolCalls: [],
      complete: false,
    };
    return {
      list: [...messages, fresh],
      current: { ...fresh },
      index: messages.length,
    };
  };

  switch (event.kind) {
    case "text_delta": {
      const { list, current, index } = ensureAssistant();
      current.text = current.text + (event.text ?? "");
      list[index] = current;
      return list;
    }
    case "tool_use": {
      const { list, current, index } = ensureAssistant();
      const call: ToolCallEntry = {
        tool_call_id: event.tool_call_id ?? `call-${current.toolCalls.length}`,
        tool_name: event.tool_name ?? "tool",
        tool_input: event.tool_input ?? {},
        done: false,
      };
      current.toolCalls = [...current.toolCalls, call];
      list[index] = current;
      return list;
    }
    case "tool_result": {
      const { list, current, index } = ensureAssistant();
      const callId = event.tool_call_id;
      current.toolCalls = current.toolCalls.map((c) =>
        c.tool_call_id === callId
          ? { ...c, tool_output: event.tool_output, done: true }
          : c,
      );
      list[index] = current;
      return list;
    }
    case "final": {
      const { list, current, index } = ensureAssistant();
      if (event.text) current.text = current.text + event.text;
      current.complete = true;
      list[index] = current;
      return list;
    }
    case "error": {
      const { list, current, index } = ensureAssistant();
      current.error = event.error_message ?? "Agent error";
      current.complete = true;
      list[index] = current;
      return list;
    }
    default:
      // approval_request / approval_granted / approval_denied don't change the
      // message list directly — the hook surfaces them via `pendingApprovals`.
      return messages;
  }
}

export function useAgentStream(
  opts: UseAgentStreamOptions,
): UseAgentStreamResult {
  const { client, sessionId } = opts;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>(
    [],
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<VoyagentApiError | Error | null>(null);
  const [lastEventId, setLastEventId] = useState<string | null>(null);

  /**
   * Guards against concurrent sends within one session. We serialize writes
   * rather than trying to multiplex turns — the runtime contract only
   * supports one active turn per session at a time.
   */
  const inFlightRef = useRef<Promise<void> | null>(null);

  const drain = useCallback(
    async (
      text: string,
      approvals?: Record<string, boolean>,
    ): Promise<void> => {
      setError(null);
      setIsStreaming(true);

      // Append a user bubble immediately for responsiveness. Empty-text
      // resumption turns (pure approval resolutions) don't warrant a bubble.
      if (text.length > 0) {
        setMessages((prev) => [
          ...prev,
          {
            kind: "user",
            id: newId(),
            text,
            timestamp: nowIso(),
          },
        ]);
      }

      try {
        const iter = client.sendMessage(sessionId, {
          message: text,
          approvals: approvals ?? null,
          onLastEventId: (id) => setLastEventId(id),
        });

        for await (const event of iter) {
          // Approval plumbing: the runtime pauses after emitting a request.
          if (event.kind === "approval_request") {
            setPendingApprovals((prev) => {
              if (prev.some((p) => p.approval_id === event.approval_id))
                return prev;
              return [
                ...prev,
                {
                  approval_id: event.approval_id ?? "unknown",
                  summary: event.approval_summary ?? "Approval required",
                  turn_id: event.turn_id,
                },
              ];
            });
            continue;
          }

          if (
            event.kind === "approval_granted" ||
            event.kind === "approval_denied"
          ) {
            setPendingApprovals((prev) =>
              prev.filter((p) => p.approval_id !== event.approval_id),
            );
            continue;
          }

          setMessages((prev) => reduceEvent(prev, event));

          if (event.kind === "final" || event.kind === "error") {
            // Stream may still yield (heartbeats filtered upstream), but the
            // turn is logically done. The async iterator will resolve itself
            // once the server closes the connection.
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setIsStreaming(false);
      }
    },
    [client, sessionId],
  );

  const send = useCallback(
    async (
      text: string,
      approvals?: Record<string, boolean>,
    ): Promise<void> => {
      // Serialize: wait on any currently-running drain before starting.
      const prior = inFlightRef.current;
      const next = (async () => {
        if (prior) {
          try {
            await prior;
          } catch {
            /* swallow; surfaced through state */
          }
        }
        await drain(text, approvals);
      })();
      inFlightRef.current = next;
      try {
        await next;
      } finally {
        if (inFlightRef.current === next) inFlightRef.current = null;
      }
    },
    [drain],
  );

  const respondToApproval = useCallback(
    async (approvalId: string, granted: boolean): Promise<void> => {
      // Optimistically clear the approval so the UI stops blocking.
      setPendingApprovals((prev) =>
        prev.filter((p) => p.approval_id !== approvalId),
      );
      await send("", { [approvalId]: granted });
    },
    [send],
  );

  return {
    messages,
    pendingApprovals,
    isStreaming,
    error,
    lastEventId,
    send,
    respondToApproval,
  };
}
