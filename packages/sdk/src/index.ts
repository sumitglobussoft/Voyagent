/**
 * @voyagent/sdk
 *
 * Typed HTTP + SSE client for the Voyagent FastAPI backend. This is the ONLY
 * supported way for TypeScript clients (Web, Desktop, Mobile) to talk to the
 * Voyagent API — all request/response shapes flow through here, all retries
 * and error handling land here, all auth/tenancy injection is centralized
 * here.
 *
 * v0 surface: `health()` and `moneySchema()`. Streaming helper `streamSSE` is
 * scaffolding for when the agent runtime lands.
 */
export { VoyagentClient } from "./client.js";
export type { VoyagentClientOptions } from "./client.js";
export { VoyagentApiError } from "./errors.js";
export { streamSSE } from "./sse.js";
export type { SSEEvent } from "./sse.js";
export type * from "./types.js";
