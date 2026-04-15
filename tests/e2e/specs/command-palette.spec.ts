// Cmd+K command palette spec.
//
// Exercises the global ⌘K / Ctrl+K listener, the fuzzy matcher, the
// Enter-to-navigate flow, Escape-to-close, and the "no matches" empty
// state. The palette is a client component mounted via
// CommandPaletteProvider in AppProviders, so it lives on every authed
// page — we use /app/chat as the landing surface.

import { test, expect } from "../fixtures/authed";

test.describe("command palette", () => {
  test("Cmd+K opens, filters, navigates, Escape closes", async ({
    authedPage,
  }) => {
    const page = authedPage;

    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });

    // Open via Meta+K (macOS) and Control+K (others). Playwright's
    // Meta+K fires the metaKey; the provider listens for either
    // metaKey or ctrlKey so one chord covers both.
    await page.keyboard.press("Meta+K");

    let palette = page.getByTestId("command-palette");
    if (!(await palette.isVisible().catch(() => false))) {
      // Fallback: some keyboards / OSes don't translate Meta to
      // metaKey on Playwright's synthetic events. Control+K is the
      // documented Windows/Linux shortcut the provider also listens
      // for.
      await page.keyboard.press("Control+K");
      palette = page.getByTestId("command-palette");
    }
    await expect(palette).toBeVisible({ timeout: 5_000 });
    await expect(palette).toHaveAttribute("aria-modal", "true");

    const input = page.getByTestId("command-palette-input");
    await expect(input).toBeFocused();

    // Type "enq" — the fuzzy matcher keeps "Enquiries" and drops
    // unrelated commands like "Audit log" and "Profile".
    await input.fill("enq");
    await expect(page.getByTestId("command-palette-item-enquiries")).toBeVisible();
    await expect(page.getByTestId("command-palette-item-audit")).toHaveCount(0);

    // Enter navigates to /app/enquiries.
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/app\/enquiries(\?|$)/, { timeout: 10_000 });
    await expect(page).toHaveURL(/\/app\/enquiries(\?|$)/);

    // Re-open the palette and assert Escape closes it.
    await page.keyboard.press("Control+K");
    const palette2 = page.getByTestId("command-palette");
    await expect(palette2).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press("Escape");
    await expect(palette2).toHaveCount(0);

    // Re-open and type nonsense — "No matches" empty state renders.
    await page.keyboard.press("Control+K");
    await expect(page.getByTestId("command-palette")).toBeVisible();
    await page.getByTestId("command-palette-input").fill("zzzxxxqqqnoop");
    await expect(page.getByTestId("command-palette-empty")).toBeVisible();
  });
});
