/**
 * @voyagent/chat — web entry.
 *
 * This file builds to `dist/index.js` and is picked by the `default`
 * condition in `package.json#exports`. The React Native entry
 * (`dist/index.native.js`) is built from `index.native.ts` and is picked
 * by Metro via the `react-native` condition.
 *
 * Hooks (`useAgentStream`) and types are platform-agnostic — both entries
 * re-export them from the same source file. Components diverge into
 * `*.web.tsx` and `*.native.tsx` variants.
 */
export { ChatWindow } from "./ChatWindow.web.js";
export type { ChatWindowProps } from "./ChatWindow.web.js";

export { MessageList } from "./MessageList.web.js";
export type { MessageListProps } from "./MessageList.web.js";

export { ComposerBar } from "./ComposerBar.web.js";
export type { ComposerBarProps } from "./ComposerBar.web.js";

export { ToolCallCard } from "./ToolCallCard.web.js";
export type { ToolCallCardProps } from "./ToolCallCard.web.js";

export { ApprovalPrompt } from "./ApprovalPrompt.web.js";
export type { ApprovalPromptProps } from "./ApprovalPrompt.web.js";

export { Markdown } from "./Markdown.web.js";
export type { MarkdownProps } from "./Markdown.web.js";

export { MessageActions } from "./MessageActions.web.js";
export type { MessageActionsProps } from "./MessageActions.web.js";

export { EmptyState, SUGGESTIONS } from "./EmptyState.web.js";
export type { EmptyStateProps } from "./EmptyState.web.js";

export { SessionHeader } from "./SessionHeader.web.js";
export type { SessionHeaderProps } from "./SessionHeader.web.js";

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
