// /api/reports/* contract checks.
//
// Pure API spec — no browser. Uses the `apiRequest` fixture for the
// authenticated cases (fresh tenant) and Playwright's bare `request`
// fixture for the 401 probe.

import { test as anon, expect } from "@playwright/test";

import { test } from "../fixtures/authed";

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

test.describe("reports — authenticated", () => {
  test("GET /api/reports/receivables returns the aging-report shape", async ({
    apiRequest,
  }) => {
    const qs = new URLSearchParams({
      from: isoDaysAgo(90),
      to: isoDaysAgo(0),
    });
    const res = await apiRequest.get(`/api/reports/receivables?${qs}`);
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;

    expect(typeof body.tenant_id).toBe("string");
    expect(body.period).toBeDefined();
    expect(body.total_outstanding).toBeDefined();
    expect(Array.isArray(body.aging_buckets)).toBe(true);
    expect((body.aging_buckets as unknown[]).length).toBe(4);
    expect(Array.isArray(body.top_debtors)).toBe(true);
  });

  test("GET /api/reports/payables returns the aging-report shape", async ({
    apiRequest,
  }) => {
    const qs = new URLSearchParams({
      from: isoDaysAgo(90),
      to: isoDaysAgo(0),
    });
    const res = await apiRequest.get(`/api/reports/payables?${qs}`);
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;

    expect(typeof body.tenant_id).toBe("string");
    expect(body.period).toBeDefined();
    expect(body.total_outstanding).toBeDefined();
    expect(Array.isArray(body.aging_buckets)).toBe(true);
    expect((body.aging_buckets as unknown[]).length).toBe(4);
  });

  test("GET /api/reports/itinerary with unknown session_id returns 404", async ({
    apiRequest,
  }) => {
    // Fresh tenant has no chat sessions — any plausible UUID returns 404.
    const fakeSession = "00000000-0000-4000-8000-000000000000";
    const res = await apiRequest.get(
      `/api/reports/itinerary?session_id=${fakeSession}`,
      { failOnStatusCode: false },
    );
    expect(res.status()).toBe(404);
  });
});

anon.describe("reports — gating", () => {
  anon("unauth GET /api/reports/receivables returns 401", async ({ request }) => {
    const res = await request.get(
      `/api/reports/receivables?from=${isoDaysAgo(30)}&to=${isoDaysAgo(0)}`,
      { failOnStatusCode: false },
    );
    expect(res.status()).toBe(401);
  });
});

// Sanity: a fake session_id that isn't even a UUID should still route to
// the reports endpoint cleanly (400 or 422) rather than 500.
test("GET /api/reports/itinerary with malformed session_id is a client error", async ({
  apiRequest,
}) => {
  const res = await apiRequest.get(
    "/api/reports/itinerary?session_id=not-a-uuid",
    { failOnStatusCode: false },
  );
  const status = res.status();
  expect([400, 404, 422]).toContain(status);
});
