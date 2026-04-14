// Public API smoke checks.
//
// - /api/health        : 200 + {"status":"ok"}
// - /api/schemas/money : 200 + JSON with a $schema or type field
// - /api/openapi.json  : 200 + JSON containing "openapi"
// - /api/chat/*        : expected to fail without auth or because the
//                        agent runtime is not yet wired. We assert the
//                        response is in a known allow-list of codes and
//                        not something unexpected like 500.

import { expect, test, type APIResponse } from "@playwright/test";

const ALLOWED_CHAT_STATUSES = new Set([401, 403, 404, 503, 307, 308]);

function expectStatusIn(
  res: APIResponse,
  allowed: Set<number>,
  context: string,
): void {
  const status = res.status();
  expect(
    allowed.has(status),
    `${context}: expected one of ${[...allowed].join(
      ", ",
    )} but got ${status}`,
  ).toBe(true);
}

test.describe("api smoke", () => {
  test("/api/health returns 200 + ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
    const json = (await res.json()) as { status?: unknown };
    expect(json.status).toBe("ok");
  });

  test("/api/schemas/money returns a JSON schema", async ({ request }) => {
    const res = await request.get("/api/schemas/money");
    expect(res.status()).toBe(200);
    const ct = res.headers()["content-type"] ?? "";
    expect(ct).toMatch(/application\/json/i);
    const json = (await res.json()) as Record<string, unknown>;
    const hasSchemaField =
      "$schema" in json || "type" in json || "properties" in json;
    expect(hasSchemaField).toBe(true);
  });

  test("/api/openapi.json is served", async ({ request }) => {
    const res = await request.get("/api/openapi.json");
    expect(res.status()).toBe(200);
    const json = (await res.json()) as Record<string, unknown>;
    expect(Object.keys(json)).toContain("openapi");
  });

  test("POST /api/chat/sessions without auth is in allowed error set", async ({
    request,
  }) => {
    const res = await request.post("/api/chat/sessions", {
      data: {},
      failOnStatusCode: false,
      maxRedirects: 0,
    });
    expectStatusIn(
      res,
      ALLOWED_CHAT_STATUSES,
      "POST /api/chat/sessions",
    );
  });

  test("GET /api/chat/sessions/does-not-exist without auth is in allowed error set", async ({
    request,
  }) => {
    const res = await request.get("/api/chat/sessions/does-not-exist", {
      failOnStatusCode: false,
      maxRedirects: 0,
    });
    expectStatusIn(
      res,
      ALLOWED_CHAT_STATUSES,
      "GET /api/chat/sessions/does-not-exist",
    );
  });
});
