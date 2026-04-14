// Parametrized smoke test across every top-nav route.
//
// For each nav entry: navigate, expect a 2xx response, expect at least
// one visible heading (H1 on the landing page, H2 on subpages that use
// SectionHeader), and expect the <title> to include "Voyagent".
//
// Also verifies the Sign-in CTA points at /app.

import { expect, test } from "@playwright/test";

const NAV_ROUTES: Array<{ path: string; label: string }> = [
  { path: "/", label: "Home" },
  { path: "/product", label: "Product" },
  { path: "/features", label: "Features" },
  { path: "/architecture", label: "Architecture" },
  { path: "/integrations", label: "Integrations" },
  { path: "/security", label: "Security" },
  { path: "/pricing", label: "Pricing" },
  { path: "/about", label: "About" },
  { path: "/contact", label: "Contact" },
  { path: "/docs/ARCHITECTURE", label: "Docs" },
];

test.describe("marketing nav routes", () => {
  for (const route of NAV_ROUTES) {
    test(`${route.label} (${route.path}) renders`, async ({ page }) => {
      const response = await page.goto(route.path);
      expect(response, `no response for ${route.path}`).not.toBeNull();
      const status = response!.status();
      expect(
        status >= 200 && status < 400,
        `expected 2xx/3xx for ${route.path}, got ${status}`,
      ).toBe(true);

      await test.step("title contains Voyagent", async () => {
        await expect(page).toHaveTitle(/voyagent/i);
      });

      await test.step("a top-level heading is visible", async () => {
        // Only `/` has an H1 (Hero). Subpages use SectionHeader which
        // emits H2. Accept either and assert at least one is visible.
        const h1 = page.getByRole("heading", { level: 1 }).first();
        const h2 = page.getByRole("heading", { level: 2 }).first();
        const h1Count = await h1.count();
        if (h1Count > 0) {
          await expect(h1).toBeVisible();
        } else {
          await expect(h2).toBeVisible();
        }
      });
    });
  }

  test("top nav sign-in CTA points at /app", async ({ page }) => {
    await page.goto("/");
    const signIn = page.getByRole("link", { name: /^sign in$/i }).first();
    await expect(signIn).toHaveAttribute("href", "/app");
  });
});
