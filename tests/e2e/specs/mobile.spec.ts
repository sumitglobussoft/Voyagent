// Mobile-only coverage for the narrow-viewport drawer.
//
// Runs only under the ``chromium-mobile`` project (Pixel 5 preset);
// the top-level ``test.skip`` below bails out for desktop projects so
// the suite reports ``skipped`` instead of failing on a device that
// never renders the hamburger.
//
// These tests use the shared ``authedPage`` fixture from
// ``fixtures/authed.ts`` so each run starts with a fresh tenant and
// the ``voyagent_at`` cookie already seeded.

import { expect, test } from "../fixtures/authed";

test.describe("mobile navigation drawer", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile-only");

  test("hamburger opens the drawer and shows workspace nav", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });

    const hamburger = page.getByRole("button", { name: /open menu/i });
    await expect(hamburger).toBeVisible();
    await expect(hamburger).toHaveAttribute("aria-expanded", "false");

    await hamburger.click();
    await expect(hamburger).toHaveAttribute("aria-expanded", "true");

    const drawer = page.getByRole("dialog", { name: /primary navigation/i });
    await expect(drawer).toBeVisible();

    // The drawer reuses SidebarContent, so every workspace link must
    // be present — same nav items the desktop sidebar renders.
    for (const label of ["Chat", "Enquiries", "Approvals", "Audit"]) {
      await expect(
        drawer.getByRole("link", { name: new RegExp(`^${label}$`) }),
      ).toBeVisible();
    }
  });

  test("clicking a nav link navigates and closes the drawer", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /open menu/i }).click();
    const drawer = page.getByRole("dialog", { name: /primary navigation/i });
    await expect(drawer).toBeVisible();

    await Promise.all([
      page.waitForURL(/\/app\/enquiries(?:\?|$)/, { timeout: 15_000 }),
      drawer.getByRole("link", { name: /^Enquiries$/ }).click(),
    ]);

    // Drawer should auto-dismiss on nav-link tap.
    await expect(drawer).toBeHidden();
  });

  test("Escape key closes the drawer", async ({ authedPage: page }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /open menu/i }).click();
    const drawer = page.getByRole("dialog", { name: /primary navigation/i });
    await expect(drawer).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
  });

  test("tapping the backdrop closes the drawer", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /open menu/i }).click();
    const drawer = page.getByRole("dialog", { name: /primary navigation/i });
    await expect(drawer).toBeVisible();

    // The backdrop is aria-hidden decorative, so locate it by class.
    const backdrop = page.locator(
      '.voyagent-drawer-backdrop[data-open="true"]',
    );
    // Click on the right edge so we don't accidentally hit the panel.
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("viewport size unavailable");
    await backdrop.click({
      position: { x: viewport.width - 20, y: viewport.height / 2 },
    });
    await expect(drawer).toBeHidden();
  });

  test("drawer contains the same workspace items as the desktop sidebar", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: /open menu/i }).click();
    const drawer = page.getByRole("dialog", { name: /primary navigation/i });

    const expected = ["Chat", "Enquiries", "Approvals", "Audit"];
    for (const label of expected) {
      await expect(
        drawer.getByRole("link", { name: new RegExp(`^${label}$`) }),
      ).toBeVisible();
    }
    // And the "New chat" pill from the top of SidebarContent.
    await expect(
      drawer.getByRole("link", { name: /new chat/i }),
    ).toBeVisible();
  });
});
