// Theme toggle / dark mode specs.
//
// Covers the user-facing contract of the ThemeProvider + ThemeToggle
// pair:
//   1. Unauthenticated visitors see light mode by default.
//   2. Signed-in users can toggle the theme from the sidebar UserCard
//      and the resulting `dark` class + `voyagent_theme` cookie stick.
//   3. The preference survives a hard reload.
//   4. Toggling back to light removes the class and updates the cookie.
//
// These tests stand in for unit coverage since apps/web doesn't have
// vitest wired up — Playwright exercises the same state transitions
// end-to-end.

import { expect, test } from "../fixtures/authed";

test.describe("dark mode theme toggle", () => {
  test("unauthenticated root page defaults to light mode", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const htmlClass = await page.locator("html").getAttribute("class");
    // The class may be null/empty but should NOT contain `dark` on the
    // first visit from a clean browser state.
    expect(htmlClass ?? "").not.toContain("dark");
  });

  test("signed-in user can toggle theme, cookie + class persist across reload", async ({
    authedPage,
  }) => {
    await authedPage.goto("/app/chat", { waitUntil: "domcontentloaded" });

    // Sanity: theme toggle is in the sidebar and accessible by test id.
    const toggle = authedPage.getByTestId("theme-toggle");
    await expect(toggle).toBeVisible();

    // First click: flip to dark.
    await toggle.click();
    await expect(authedPage.locator("html")).toHaveClass(/dark/);

    const cookiesDark = await authedPage.context().cookies();
    const themeCookieDark = cookiesDark.find((c) => c.name === "voyagent_theme");
    expect(themeCookieDark?.value).toBe("dark");

    // Hard reload — the class should still apply after rehydration.
    await authedPage.reload({ waitUntil: "domcontentloaded" });
    await expect(authedPage.locator("html")).toHaveClass(/dark/);

    // Second click: flip back to light.
    await authedPage.getByTestId("theme-toggle").click();
    await expect(authedPage.locator("html")).not.toHaveClass(/dark/);

    const cookiesLight = await authedPage.context().cookies();
    const themeCookieLight = cookiesLight.find((c) => c.name === "voyagent_theme");
    expect(themeCookieLight?.value).toBe("light");
  });
});
