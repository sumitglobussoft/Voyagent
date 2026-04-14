/**
 * @voyagent/chat — React Native entry.
 *
 * Built to `dist/index.native.js`. Metro resolves this via the
 * `react-native` condition in `package.json#exports`. Vite / Next on
 * the web never reach this file.
 *
 * The hook and types are the same as the web entry; components come
 * from their `.native.tsx` siblings which render with `View`, `FlatList`,
 * `TextInput`, `Pressable` rather than DOM elements.
 */
export { ChatWindow } from "./ChatWindow.native.js";
export type { ChatWindowProps } from "./ChatWindow.native.js";

export { MessageList } from "./MessageList.native.js";
export type { MessageListProps } from "./MessageList.native.js";

export { ComposerBar } from "./ComposerBar.native.js";
export type { ComposerBarProps } from "./ComposerBar.native.js";

export { ToolCallCard } from "./ToolCallCard.native.js";
export type { ToolCallCardProps } from "./ToolCallCard.native.js";

export { ApprovalPrompt } from "./ApprovalPrompt.native.js";
export type { ApprovalPromptProps } from "./ApprovalPrompt.native.js";

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
