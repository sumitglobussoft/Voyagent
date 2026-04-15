"use client";

/**
 * The message transcript.
 *
 * Uses `role="log"` + `aria-live="polite"` so screen readers announce new
 * agent output as it streams in. Auto-scrolls to the bottom whenever the
 * message list grows or the tail message mutates (text deltas).
 *
 * Assistant messages render through the shared `Markdown` component so
 * bold/italic/lists/tables format nicely. User messages stay as plain
 * text — accidental markdown in a typed prompt shouldn't be re-formatted.
 */
import { useEffect, useRef, type ReactElement } from "react";

import { Markdown } from "./Markdown.web.js";
import { MessageActions } from "./MessageActions.web.js";
import { ToolCallCard } from "./ToolCallCard.web.js";
import type { ChatMessage } from "./types.js";

export interface MessageListProps {
  messages: ChatMessage[];
  /** True while the latest turn is still streaming. */
  isStreaming?: boolean;
  /**
   * Re-run the given user message. When omitted the Regenerate button is
   * hidden entirely.
   */
  onRegenerate?: (userMessageId: string) => void | Promise<void>;
}

export function MessageList({
  messages,
  isStreaming = false,
  onRegenerate,
}: MessageListProps): ReactElement {
  const endRef = useRef<HTMLDivElement | null>(null);

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

  // Index of the last assistant message (for the "is latest" flag).
  let lastAssistantIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.kind === "assistant") {
      lastAssistantIdx = i;
      break;
    }
  }

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Agent conversation"
      className="voyagent-scroll-y flex flex-1 flex-col"
    >
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 md:px-6 md:py-8">
      {messages.map((message, i) => {
        if (message.kind === "user") {
          // The previous assistant bubble before the next user message
          // should render "faded" once a regenerate has replaced it, but
          // we don't track that explicitly — the regenerate handler trims
          // the list, so nothing needs fading here.
          return (
            <UserBubble
              key={message.id}
              text={message.text}
              messageId={message.id}
            />
          );
        }
        const isLatestAssistant = i === lastAssistantIdx;
        // Look up the preceding user message id so Regenerate can call back.
        let precedingUserId: string | undefined;
        for (let j = i - 1; j >= 0; j--) {
          const m = messages[j];
          if (m?.kind === "user") {
            precedingUserId = m.id;
            break;
          }
        }
        const stillStreaming = isLatestAssistant && isStreaming;
        return (
          <AssistantBubble
            key={message.id}
            message={message}
            isLatest={isLatestAssistant}
            canRegenerate={
              !!onRegenerate && !!precedingUserId && !stillStreaming
            }
            onRegenerate={
              onRegenerate && precedingUserId
                ? () => onRegenerate(precedingUserId!)
                : undefined
            }
          />
        );
      })}
      <div ref={endRef} />
    </div>
    </div>
  );
}

function UserBubble({
  text,
  messageId,
}: {
  text: string;
  messageId: string;
}): ReactElement {
  return (
    <div
      className="group flex flex-col items-end gap-1"
      data-message-id={messageId}
    >
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-neutral-900 px-4 py-3 text-[15px] leading-relaxed text-neutral-50 shadow-sm">
        {text}
      </div>
      <MessageActions text={text} />
    </div>
  );
}

function AssistantBubble({
  message,
  isLatest,
  canRegenerate,
  onRegenerate,
}: {
  message: Extract<ChatMessage, { kind: "assistant" }>;
  isLatest: boolean;
  canRegenerate: boolean;
  onRegenerate?: () => void | Promise<void>;
}): ReactElement {
  return (
    <div className="group flex items-start gap-3">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-neutral-900 to-neutral-700 text-xs font-semibold text-white shadow-sm">
        V
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="prose prose-sm max-w-none text-[15px] leading-relaxed text-neutral-900">
          {message.text.length > 0 ? <Markdown text={message.text} /> : null}
          {message.toolCalls.map((call) => (
            <ToolCallCard key={call.tool_call_id} call={call} />
          ))}
          {message.error !== undefined ? (
            <div
              role="alert"
              className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              {message.error}
            </div>
          ) : null}
        </div>
        {message.complete ? (
          <MessageActions
            text={message.text}
            canRegenerate={canRegenerate}
            onRegenerate={onRegenerate}
            alwaysVisible={isLatest}
          />
        ) : null}
      </div>
    </div>
  );
}
