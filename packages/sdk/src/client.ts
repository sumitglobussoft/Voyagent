/**
 * VoyagentClient — typed HTTP client for the Voyagent API.
 *
 * Runtime-agnostic: uses only native `fetch`, no Node-only APIs. Works in
 * browsers, Node 20+, and React Native.
 */
import type {
  AgentEvent,
  SendMessageInput,
  SessionCreateInput,
  SessionSummary,
} from "./chat.js";
import { VoyagentApiError } from "./errors.js";
import { streamSSE } from "./sse.js";

export interface VoyagentClientOptions {
  /** Base URL of the Voyagent API, e.g. `http://localhost:8000`. No trailing slash required. */
  baseUrl: string;
  /** Inject a custom fetch (e.g. for tests, MSW, or a polyfilled RN env). Defaults to global `fetch`. */
  fetchImpl?: typeof fetch;
  /** Tenant ID, sent as `X-Voyagent-Tenant`. */
  tenantId?: string;
  /**
   * Auth token, sent as `Authorization: Bearer <token>`. May be a literal string
   * or an async getter so SPA consumers can refresh a session token lazily.
   */
  authToken?: string | (() => Promise<string>);
}

const MAX_ERROR_BODY_PREVIEW = 512;

export class VoyagentClient {
  readonly #baseUrl: string;
  readonly #fetch: typeof fetch;
  readonly #tenantId: string | undefined;
  readonly #authToken: string | (() => Promise<string>) | undefined;

  constructor(opts: VoyagentClientOptions) {
    this.#baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.#fetch = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.#tenantId = opts.tenantId;
    this.#authToken = opts.authToken;
  }

  /** The base URL the client was configured with (no trailing slash). */
  get baseUrl(): string {
    return this.#baseUrl;
  }

  /** GET /health — liveness probe. */
  async health(): Promise<{ status: "ok" }> {
    return this.#request<{ status: "ok" }>("/health");
  }

  /** GET /schemas/money — returns the JSON Schema for the canonical Money type. */
  async moneySchema(): Promise<Record<string, unknown>> {
    return this.#request<Record<string, unknown>>("/schemas/money");
  }

  // ------------------------------------------------------------------- //
  // Chat surface.                                                       //
  // ------------------------------------------------------------------- //

  /** POST /chat/sessions — create a new chat session. */
  async createSession(input: SessionCreateInput): Promise<{ session_id: string }> {
    return this.#request<{ session_id: string }>("/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  }

  /** GET /chat/sessions/{id} — metadata (no message bodies). */
  async getSession(id: string): Promise<SessionSummary> {
    return this.#request<SessionSummary>(
      `/chat/sessions/${encodeURIComponent(id)}`,
    );
  }

  /**
   * POST /chat/sessions/{id}/messages — drive one agent turn as an async
   * iterable of {@link AgentEvent} objects.
   *
   * The returned iterable completes when the server closes the stream (after
   * a `final`-kind event, or a runtime error, or the client aborting via
   * `input.signal`). `heartbeat` SSE frames are silently dropped.
   */
  async *sendMessage(
    sessionId: string,
    input: SendMessageInput,
  ): AsyncIterable<AgentEvent> {
    const url = `${this.#baseUrl}/chat/sessions/${encodeURIComponent(sessionId)}/messages`;
    const headers = await this.#buildHeaders({
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    });

    const body = JSON.stringify({
      message: input.message,
      approvals: input.approvals ?? null,
    });

    const iter = streamSSE<AgentEvent>(url, {
      method: "POST",
      headers,
      body,
      signal: input.signal,
    });

    for await (const ev of iter) {
      if (ev.event === "heartbeat") continue;
      if (ev.event !== "agent_event") continue;
      yield ev.data;
    }
  }

  async #buildHeaders(seed: Record<string, string>): Promise<Headers> {
    const headers = new Headers(seed);
    if (this.#tenantId) headers.set("X-Voyagent-Tenant", this.#tenantId);
    if (this.#authToken) {
      const token =
        typeof this.#authToken === "function"
          ? await this.#authToken()
          : this.#authToken;
      headers.set("Authorization", `Bearer ${token}`);
    }
    return headers;
  }

  async #request<T>(path: string, init?: RequestInit): Promise<T> {
    const method = init?.method ?? "GET";
    const url = `${this.#baseUrl}${path.startsWith("/") ? path : `/${path}`}`;

    const headers = await this.#buildHeaders({});
    // Merge caller-supplied headers on top.
    if (init?.headers) {
      const incoming = new Headers(init.headers);
      incoming.forEach((value, key) => headers.set(key, value));
    }
    if (!headers.has("Accept")) headers.set("Accept", "application/json");

    const response = await this.#fetch(url, { ...init, method, headers });

    if (!response.ok) {
      const raw = await response.text().catch(() => "");
      throw new VoyagentApiError({
        status: response.status,
        method,
        path,
        responseBodyPreview: raw.slice(0, MAX_ERROR_BODY_PREVIEW),
      });
    }

    // 204 No Content or empty body.
    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }
}
