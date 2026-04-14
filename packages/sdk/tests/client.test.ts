/**
 * Tests for VoyagentClient — the typed HTTP surface of the SDK.
 *
 * All network I/O is mocked via an injected fetch implementation
 * (`fetchImpl`) so no real sockets are involved. These tests assert the
 * contract every other package silently depends on: auth headers are
 * attached, URLs are built without double-slashes, errors are mapped
 * into `VoyagentApiError`, and JSON bodies go out in snake_case.
 */
import { describe, expect, it, vi } from "vitest";

import { VoyagentClient } from "../src/client.js";
import { VoyagentApiError } from "../src/errors.js";

/** Build a `fetch` double that returns the given canned JSON response. */
function okJsonFetch<T>(body: T, status = 200) {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

function errorFetch(status: number, raw = '{"detail":"boom"}') {
  return vi.fn(async () => {
    return new Response(raw, { status });
  });
}

describe("VoyagentClient — URL construction", () => {
  it("strips trailing slashes from baseUrl so the final path has no double slash", async () => {
    const fetchImpl = okJsonFetch({ status: "ok" });
    const client = new VoyagentClient({
      baseUrl: "https://api.example.com////",
      fetchImpl,
    });

    await client.health();

    expect(client.baseUrl).toBe("https://api.example.com");
    const call = fetchImpl.mock.calls[0]?.[0];
    expect(String(call)).toBe("https://api.example.com/health");
  });

  it("builds absolute URL from leading-slashed path", async () => {
    const fetchImpl = okJsonFetch({ foo: 1 });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await client.moneySchema();

    expect(String(fetchImpl.mock.calls[0]?.[0])).toBe(
      "http://localhost:8000/schemas/money",
    );
  });

  it("URL-encodes session ids so pathological characters don't break the URL", async () => {
    const fetchImpl = okJsonFetch({
      session_id: "x",
      tenant_id: "t",
      actor_id: "a",
      message_count: 0,
      pending_approvals: [],
    });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await client.getSession("weird/id with spaces");

    const url = String(fetchImpl.mock.calls[0]?.[0]);
    expect(url).toBe(
      "http://localhost:8000/chat/sessions/weird%2Fid%20with%20spaces",
    );
  });
});

describe("VoyagentClient — auth and tenant headers", () => {
  it("omits Authorization when no authToken is configured", async () => {
    const fetchImpl = okJsonFetch({ status: "ok" });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await client.health();

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = new Headers(init?.headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("attaches Authorization: Bearer <token> on every request when a static token is set", async () => {
    const fetchImpl = okJsonFetch({ status: "ok" });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      authToken: "tok-123",
      fetchImpl,
    });

    await client.health();
    await client.moneySchema();

    for (const [, init] of fetchImpl.mock.calls) {
      const headers = new Headers((init as RequestInit).headers);
      expect(headers.get("Authorization")).toBe("Bearer tok-123");
    }
  });

  it("resolves an async authToken getter on each request", async () => {
    const fetchImpl = okJsonFetch({ status: "ok" });
    const getter = vi.fn(async () => "refreshed-tok");
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      authToken: getter,
      fetchImpl,
    });

    await client.health();
    await client.health();

    expect(getter).toHaveBeenCalledTimes(2);
    const headers = new Headers(
      (fetchImpl.mock.calls[1]?.[1] as RequestInit).headers,
    );
    expect(headers.get("Authorization")).toBe("Bearer refreshed-tok");
  });

  it("attaches X-Voyagent-Tenant when tenantId is configured", async () => {
    const fetchImpl = okJsonFetch({ status: "ok" });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      tenantId: "tenant-A",
      fetchImpl,
    });

    await client.health();

    const headers = new Headers(
      (fetchImpl.mock.calls[0]?.[1] as RequestInit).headers,
    );
    expect(headers.get("X-Voyagent-Tenant")).toBe("tenant-A");
  });
});

describe("VoyagentClient — body serialization", () => {
  it("sends createSession bodies as JSON with snake_case keys (not form-encoded)", async () => {
    const fetchImpl = okJsonFetch({ session_id: "s1" });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await client.createSession({ tenant_id: "T", actor_id: "A" });

    const [, init] = fetchImpl.mock.calls[0] ?? [];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    const body = (init as RequestInit).body;
    expect(typeof body).toBe("string");
    expect(JSON.parse(body as string)).toEqual({
      tenant_id: "T",
      actor_id: "A",
    });
  });

  it("uses POST for createSession", async () => {
    const fetchImpl = okJsonFetch({ session_id: "s1" });
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await client.createSession({ tenant_id: "T", actor_id: "A" });

    expect(fetchImpl.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
  });
});

describe("VoyagentClient — error mapping", () => {
  it("wraps non-2xx responses into VoyagentApiError with status/method/path populated", async () => {
    const fetchImpl = errorFetch(404, '{"detail":"not found"}');
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await expect(client.getSession("missing")).rejects.toBeInstanceOf(
      VoyagentApiError,
    );
    try {
      await client.getSession("missing");
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(VoyagentApiError);
      const api = err as VoyagentApiError;
      expect(api.status).toBe(404);
      expect(api.method).toBe("GET");
      expect(api.path).toBe("/chat/sessions/missing");
      expect(api.responseBodyPreview).toContain("not found");
    }
  });

  it("maps 5xx to VoyagentApiError — SDK does NOT auto-retry plain requests", async () => {
    const fetchImpl = errorFetch(503, "service unavailable");
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    await expect(client.health()).rejects.toBeInstanceOf(VoyagentApiError);
    // Exactly one call — no retry helper on the plain HTTP surface.
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("truncates oversized error bodies to MAX_ERROR_BODY_PREVIEW chars", async () => {
    const huge = "x".repeat(2000);
    const fetchImpl = errorFetch(500, huge);
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    try {
      await client.health();
    } catch (err) {
      const api = err as VoyagentApiError;
      expect(api.responseBodyPreview.length).toBeLessThanOrEqual(512);
    }
  });
});

describe("VoyagentClient — 204 handling", () => {
  it("returns undefined for 204 No Content", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    const client = new VoyagentClient({
      baseUrl: "http://localhost:8000",
      fetchImpl,
    });

    const result = await client.health();
    expect(result).toBeUndefined();
  });
});
