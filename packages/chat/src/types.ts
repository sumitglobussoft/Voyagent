/**
 * Chat UI types — a narrow view on top of `AgentEvent` optimized for the
 * React layer. The hook in `useAgentStream.ts` fans out the raw event stream
 * into these structures so individual components don't have to re-coalesce
 * text deltas or pair tool calls with their results.
 */
import type { AgentEvent } from "@voyagent/sdk";

/** A single tool invocation observed inside an assistant turn. */
export interface ToolCallEntry {
  tool_call_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  /** Set when the matching `tool_result` event arrives. */
  tool_output?: Record<string, unknown>;
  /** True once the `tool_result` has been observed. */
  done: boolean;
}

/** A pending approval request the UI must surface to the operator. */
export interface ApprovalRequest {
  approval_id: string;
  summary: string;
  /** The turn this approval was requested inside, for correlation. */
  turn_id: string;
}

/**
 * A rendered message bubble. User messages are synthesized locally when the
 * operator calls `send()`; assistant messages are accreted from `text_delta`
 * events (coalesced by `turn_id`) and interleaved `ToolCallEntry`s.
 */
export type ChatMessage =
  | {
      kind: "user";
      id: string;
      text: string;
      timestamp: string;
    }
  | {
      kind: "assistant";
      id: string; // turn_id
      text: string;
      timestamp: string;
      toolCalls: ToolCallEntry[];
      /** True once a `final` event for this turn_id has been seen. */
      complete: boolean;
      /** Set when a terminal `error` event concluded this turn. */
      error?: string;
    };

export type { AgentEvent };
