// 404 + error-page specs.
//
// Exercises the new global not-found pages on both apps/web and
// apps/marketing. We deliberately use plain `test` (not the authed
// fixture) because the public 404 and marketing 404 must render
// without any session cookie.

import { expect, test } from "@playwright/test";

test.describe("error pages", () => {
  test("web app unknown path renders the authed 404 with a go-home link", async ({
    page,
  }) => {
    // Unauth visit to an `/app/*` path redirects to /sign-in — hit a
    // path under the public tree instead that definitely doesn't exist.
    const resp = await page.goto("/definitely-not-a-real-route-xyz", {
      waitUntil: "domcontentloaded",
    });
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: /page not found/i })).toBeVisible();

    const goHome = page.getByRole("link", { name: /go home/i }).first();
    await expect(goHome).toBeVisible();
    await goHome.click();
    await expect(page).toHaveURL(/\/($|\?)/);
  });

  test("marketing unknown path renders the marketing 404", async ({ page }) => {
    // The marketing site is served at the root host with `/app/*`
    // reverse-proxied to Next. A path outside `/app` and outside any
    // known marketing route should hit the marketing not-found.
    const resp = await page.goto("/does-not-exist-marketing-xyz", {
      waitUntil: "domcontentloaded",
    });
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: /page not found/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /go home/i })).toBeVisible();
  });
});
