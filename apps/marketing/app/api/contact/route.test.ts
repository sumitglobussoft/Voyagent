// Tests for the /api/contact rate limiter.
//
// Run with:
//   pnpm --filter @voyagent/marketing exec tsx --test app/api/contact/route.test.ts
//
// These are plain node:test cases that drive the POST handler directly.
// No HTTP server, no network, no Playwright — just construct a Request,
// call POST, assert on the Response. That keeps the test boundary tight
// around the limiter, which is the thing we actually changed.

import { strict as assert } from "node:assert";
import { describe, it, beforeEach } from "node:test";

import { POST } from "./route";
import { resetForTests as __resetRateLimiterForTests } from "./_limiter";

function makeRequest(overrides: {
  ip?: string;
  email?: string;
  name?: string;
  message?: string;
}) {
  const ip = overrides.ip ?? "203.0.113.7";
  const body = {
    name: overrides.name ?? "Playwright Tester",
    email: overrides.email ?? "tester@mailinator.com",
    company: "E2E",
    message: overrides.message ?? "hello",
  };
  return new Request("http://localhost/api/contact", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-connecting-ip": ip,
    },
    body: JSON.stringify(body),
  });
}

describe("/api/contact rate limit", () => {
  beforeEach(() => {
    __resetRateLimiterForTests();
  });

  it("lets the first valid submission through with 200", async () => {
    const res = await POST(
      makeRequest({ ip: "203.0.113.1", email: "first@mailinator.com" }),
    );
    assert.equal(res.status, 200);
    const body = (await res.json()) as { ok: boolean };
    assert.equal(body.ok, true);
  });

  it("allows three rapid submissions from the same IP with distinct emails", async () => {
    for (let i = 0; i < 3; i += 1) {
      const res = await POST(
        makeRequest({
          ip: "203.0.113.2",
          email: `user${i}@mailinator.com`,
        }),
      );
      assert.equal(res.status, 200, `submission ${i + 1} should succeed`);
    }
  });

  it("429s the 6th submission from the same IP (per-IP limit = 5/hour)", async () => {
    for (let i = 0; i < 5; i += 1) {
      const res = await POST(
        makeRequest({
          ip: "203.0.113.3",
          email: `user${i}@mailinator.com`,
        }),
      );
      assert.equal(res.status, 200, `submission ${i + 1} should succeed`);
    }
    const res = await POST(
      makeRequest({
        ip: "203.0.113.3",
        email: "user5@mailinator.com",
      }),
    );
    assert.equal(res.status, 429);
    assert.ok(res.headers.get("Retry-After"));
  });

  it("429s a 4th submission from the same email (per-email limit = 3/day)", async () => {
    for (let i = 0; i < 3; i += 1) {
      const res = await POST(
        makeRequest({
          ip: `198.51.100.${10 + i}`,
          email: "same@mailinator.com",
        }),
      );
      assert.equal(res.status, 200, `submission ${i + 1} should succeed`);
    }
    const res = await POST(
      makeRequest({
        ip: "198.51.100.20",
        email: "same@mailinator.com",
      }),
    );
    assert.equal(res.status, 429);
  });

  it("keeps per-IP buckets independent across different IPs", async () => {
    const res1 = await POST(
      makeRequest({ ip: "203.0.113.10", email: "a@mailinator.com" }),
    );
    const res2 = await POST(
      makeRequest({ ip: "203.0.113.11", email: "b@mailinator.com" }),
    );
    assert.equal(res1.status, 200);
    assert.equal(res2.status, 200);
  });
});
