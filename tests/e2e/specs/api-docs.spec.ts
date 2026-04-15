// /docs/api — public API reference page.
//
// Fetches OpenAPI JSON from the live API at request time and renders
// a static reference. Public, no auth required. We assert:
//   1. The page returns HTML (not JSON / not a redirect).
//   2. The header renders.
//   3. At least 10 endpoint entries are listed (FastAPI exposes 20+).
//   4. The POST /auth/sign-in anchor is present.

import { test, expect } from "@playwright/test";

test.describe("api docs page", () => {
  test("/docs/api renders the live OpenAPI as HTML", async ({ page }) => {
    const response = await page.goto("/docs/api", {
      waitUntil: "domcontentloaded",
    });
    expect(response, "navigation produced a response").not.toBeNull();
    expect(response!.status(), "page must return 200").toBe(200);

    const contentType = response!.headers()["content-type"] ?? "";
    expect(contentType).toMatch(/text\/html/);

    // Page shell.
    await expect(
      page.getByRole("heading", { level: 1 }),
    ).toBeVisible({ timeout: 10_000 });

    // Endpoint list — at least 10 entries. The index shows one link
    // per endpoint, so count those.
    const index = page.getByTestId("api-docs-index");
    await expect(index).toBeVisible();
    const count = await index.locator("a").count();
    expect(
      count,
      `expected >=10 endpoints, got ${count}`,
    ).toBeGreaterThanOrEqual(10);

    // /auth/sign-in must be listed — it's one of the most-exercised
    // surfaces on the platform and a solid canary for schema drift.
    const signInEntry = page.getByTestId("api-endpoint-post-auth-sign-in");
    await expect(signInEntry).toHaveCount(1);
  });
});
