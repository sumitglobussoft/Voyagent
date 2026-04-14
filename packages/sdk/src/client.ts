/**
 * VoyagentClient — typed HTTP client for the Voyagent API.
 *
 * Runtime-agnostic: uses only native `fetch`, no Node-only APIs. Works in
 * browsers, Node 20+, and React Native.
 */
import { VoyagentApiError } from "./errors.js";

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

  /** GET /health — liveness probe. */
  async health(): Promise<{ status: "ok" }> {
    return this.#request<{ status: "ok" }>("/health");
  }

  /** GET /schemas/money — returns the JSON Schema for the canonical Money type. */
  async moneySchema(): Promise<Record<string, unknown>> {
    return this.#request<Record<string, unknown>>("/schemas/money");
  }

  async #request<T>(path: string, init?: RequestInit): Promise<T> {
    const method = init?.method ?? "GET";
    const url = `${this.#baseUrl}${path.startsWith("/") ? path : `/${path}`}`;

    const headers = new Headers(init?.headers);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");

    if (this.#tenantId) {
      headers.set("X-Voyagent-Tenant", this.#tenantId);
    }

    if (this.#authToken) {
      const token =
        typeof this.#authToken === "function" ? await this.#authToken() : this.#authToken;
      headers.set("Authorization", `Bearer ${token}`);
    }

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
