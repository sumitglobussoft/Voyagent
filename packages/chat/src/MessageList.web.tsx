"use client";

/**
 * The message transcript.
 *
 * Uses `role="log"` + `aria-live="polite"` so screen readers announce new
 * agent output as it streams in. Auto-scrolls to the bottom whenever the
 * message list grows or the tail message mutates (text deltas).
 */
import { useEffect, useRef, type ReactElement } from "react";

import { ToolCallCard } from "./ToolCallCard.js";
import type { ChatMessage } from "./types.js";

export interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps): ReactElement {
  const endRef = useRef<HTMLDivElement | null>(null);

  // Compute a lightweight signal that changes whenever the *tail* of the list
  // mutates — enough to keep streaming deltas pinned to the bottom without
  // re-running scroll on every unrelated state update.
  const tail = messages[messages.length - 1];
  const tailSignal =
    tail === undefined
      ? "empty"
      : tail.kind === "assistant"
        ? `${tail.id}:${tail.text.length}:${tail.toolCalls.length}`
        : `${tail.id}:${tail.text.length}`;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, tailSignal]);

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Agent conversation"
      className="flex flex-1 flex-col gap-3 overflow-y-auto p-4"
    >
      {messages.map((message) =>
        message.kind === "user" ? (
          <UserBubble key={message.id} text={message.text} />
        ) : (
          <AssistantBubble key={message.id} message={message} />
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}

function UserBubble({ text }: { text: string }): ReactElement {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-neutral-900 px-3 py-2 text-sm text-neutral-50 whitespace-pre-wrap">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
}: {
  message: Extract<ChatMessage, { kind: "assistant" }>;
}): ReactElement {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-lg bg-neutral-100 px-3 py-2 text-sm text-neutral-900">
        {message.text.length > 0 ? (
          <div className="whitespace-pre-wrap">{message.text}</div>
        ) : null}
        {message.toolCalls.map((call) => (
          <ToolCallCard key={call.tool_call_id} call={call} />
        ))}
        {message.error !== undefined ? (
          <div
            role="alert"
            className="mt-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700"
          >
            {message.error}
          </div>
        ) : null}
      </div>
    </div>
  );
}
