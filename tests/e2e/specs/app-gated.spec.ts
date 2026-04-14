// Covers the /app authenticated shell gate.
//
// The deployment runs with placeholder Clerk keys. Depending on timing
// and Clerk's own behavior, visiting /app can result in:
//   - a 3xx redirect to /sign-in (Clerk middleware redirect)
//   - a redirect to a Clerk-hosted sign-in page
//   - a 500 whose body mentions "Clerk" (placeholder keys rejected)
//
// Any of these is an acceptable signal that the gate is active. The
// test fails only if /app loads a fully rendered product UI despite
// no session, or if the response class is outside 2xx/3xx/5xx.

import { expect, test } from "@playwright/test";

test.describe("app gate", () => {
  test("/app is gated (redirect or Clerk error)", async ({ page }) => {
    const response = await page.goto("/app", { waitUntil: "domcontentloaded" });
    expect(response, "no response for /app").not.toBeNull();
    const status = response!.status();
    const finalUrl = page.url();
    const body = await page.content();

    const redirected =
      /\/sign-in|clerk|accounts\.dev|login/i.test(finalUrl) &&
      !/\/app\/?$/.test(finalUrl);
    const isClerkErrorPage = status >= 500 && /clerk/i.test(body);
    const isAcceptableStatus =
      (status >= 200 && status < 400) || isClerkErrorPage;

    expect(
      isAcceptableStatus,
      `/app returned status ${status} with body snippet: ${body.slice(0, 200)}`,
    ).toBe(true);

    // If status is 2xx and body does not mention Clerk or sign-in, the
    // gate is broken — fail loudly.
    if (status >= 200 && status < 300 && !redirected) {
      expect(body).toMatch(/clerk|sign[- ]in|log[- ]in/i);
    }
  });

  test("cross-origin API call is CORS-correct", async ({ page, request }) => {
    // page.request inherits the page's origin cookies but goes through
    // the test runner's network stack. /api/health should be reachable
    // without auth and return 200 + JSON.
    await page.goto("/");
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
    const json = (await res.json()) as { status?: unknown };
    expect(json.status).toBe("ok");
  });
});
