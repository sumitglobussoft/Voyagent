/**
 * @voyagent/chat — React chat UI for the Voyagent agent runtime.
 *
 * Exports the top-level `<ChatWindow>` plus the primitives it's composed of
 * (`MessageList`, `ComposerBar`, `ToolCallCard`, `ApprovalPrompt`) and the
 * `useAgentStream` hook for consumers who want to build their own layout.
 *
 * Components are client-only — they use hooks and talk to the SDK over
 * fetch + SSE. All files are annotated with `"use client"`.
 */
export { ChatWindow } from "./ChatWindow.js";
export type { ChatWindowProps } from "./ChatWindow.js";

export { MessageList } from "./MessageList.js";
export type { MessageListProps } from "./MessageList.js";

export { ComposerBar } from "./ComposerBar.js";
export type { ComposerBarProps } from "./ComposerBar.js";

export { ToolCallCard } from "./ToolCallCard.js";
export type { ToolCallCardProps } from "./ToolCallCard.js";

export { ApprovalPrompt } from "./ApprovalPrompt.js";
export type { ApprovalPromptProps } from "./ApprovalPrompt.js";

export { useAgentStream } from "./useAgentStream.js";
export type {
  UseAgentStreamOptions,
  UseAgentStreamResult,
} from "./useAgentStream.js";

export type {
  ApprovalRequest,
  ChatMessage,
  ToolCallEntry,
} from "./types.js";
