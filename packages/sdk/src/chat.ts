/**
 * Chat-surface types for the Voyagent SDK.
 *
 * Mirrors the Python `AgentEvent` contract exposed by
 * `voyagent_agent_runtime` and framed over SSE by `services/api`. Kept as
 * hand-written TS for v0 (rather than going through `@voyagent/core`
 * codegen) because the runtime event model is owned by the runtime repo and
 * is not a canonical domain model.
 *
 * Wire format: each SSE frame is `event: agent_event` with `data:` set to
 * the JSON dump of an `AgentEvent`. Heartbeat frames (`event: heartbeat`)
 * are dropped by the client helper.
 */

/** Discriminator for {@link AgentEvent}. */
export type AgentEventKind =
  | "text_delta"
  | "tool_use"
  | "tool_result"
  | "approval_request"
  | "approval_granted"
  | "approval_denied"
  | "error"
  | "final";

/**
 * One event emitted by the agent runtime during a single conversation turn.
 *
 * All optional fields are populated only for the subset of `kind` values that
 * carry them (e.g. `text` is set for `text_delta` and `final`; `tool_name`,
 * `tool_input` for `tool_use`; etc.).
 */
export interface AgentEvent {
  kind: AgentEventKind;
  session_id: string;
  turn_id: string;
  /** ISO-8601 UTC timestamp. */
  timestamp: string;
  text?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_output?: Record<string, unknown>;
  tool_call_id?: string;
  approval_id?: string;
  approval_summary?: string;
  error_message?: string;
}

/**
 * Request body for `POST /chat/sessions`.
 *
 * The API derives tenant + actor from the bearer JWT, so the body is empty.
 * This alias is kept so call sites can still type the argument.
 */
export type SessionCreateInput = Record<string, never>;

/** Pending approval entry returned by `GET /chat/sessions/{id}`. */
export interface PendingApprovalSummary {
  approval_id: string;
  summary?: string;
}

/** Response body for `GET /chat/sessions/{id}`. */
export interface SessionSummary {
  session_id: string;
  tenant_id: string;
  actor_id: string;
  message_count: number;
  pending_approvals: PendingApprovalSummary[];
}

/** Request body for `POST /chat/sessions/{id}/messages`. */
export interface SendMessageInput {
  /** New user message text. May be empty when only resolving approvals. */
  message: string;
  /** Map of approval_id → granted. */
  approvals?: Record<string, boolean> | null;
  /** Optional abort signal — closing the underlying SSE stream. */
  signal?: AbortSignal;
  /**
   * Called once with each `id:` value observed on the SSE stream. Useful
   * for UI state that wants to display "last seen event id" or persist
   * it across a page reload. The SDK itself already threads the id
   * through on automatic reconnection — callers don't have to feed it
   * back.
   */
  onLastEventId?: (id: string) => void;
}
