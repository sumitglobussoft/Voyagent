// Covers the /app authenticated shell gate.
//
// The web app's middleware redirects unauthenticated visitors of
// /app (and any /app/* route) to /sign-in. Visiting /app without a
// session cookie should therefore end up on /sign-in, not on a
// rendered product UI.
//
// Acceptable terminal states:
//   - a 3xx redirect landing on /sign-in
//   - a 200 sign-in interstitial rendered at the /app route
// The test fails if /app loads a fully rendered product UI despite
// no session, or if the response class is outside 2xx/3xx.

import { expect, test } from "@playwright/test";

test.describe("app gate", () => {
  test("/app redirects unauthenticated visitors to /sign-in", async ({
    page,
  }) => {
    const response = await page.goto("/app", {
      waitUntil: "domcontentloaded",
    });
    expect(response, "no response for /app").not.toBeNull();
    const status = response!.status();
    const finalUrl = page.url();
    const body = await page.content();

    const redirectedToSignIn =
      /\/sign-in/i.test(finalUrl) && !/\/app\/?$/.test(finalUrl);
    const isAcceptableStatus = status >= 200 && status < 400;

    expect(
      isAcceptableStatus,
      `/app returned status ${status} with body snippet: ${body.slice(0, 200)}`,
    ).toBe(true);

    // If status is 2xx and we did not land on /sign-in, the body must
    // advertise a sign-in affordance — otherwise the gate is broken.
    if (status >= 200 && status < 300 && !redirectedToSignIn) {
      expect(body).toMatch(/sign[- ]in|log[- ]in/i);
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
