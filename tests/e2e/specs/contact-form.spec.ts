// Covers the /contact form.
//
// - Submitting with empty required fields shows a validation alert.
// - Submitting with valid fields transitions into a success state.
//
// The route handler at /api/contact only logs; we do not assert any
// email was sent.

import { expect, test } from "@playwright/test";

test.describe("contact form", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/contact");
  });

  test("shows validation error on empty submit", async ({ page }) => {
    // The form uses noValidate, so the component enforces required
    // fields itself and surfaces an inline error beneath the submit
    // button. The banner is not tagged role="alert", so we locate it
    // by its copy: "Name, email and message are required."
    await page.getByRole("button", { name: /send message/i }).click();
    // Current copy: "Name, work email, and message are required."
    const errorBanner = page.getByText(/required/i).first();
    await expect(errorBanner).toBeVisible();
    await expect(errorBanner).toContainText(/work email/i);
  });

  test("shows success state on valid submit", async ({ page }) => {
    // Use a mailinator.com address (RFC 2606-reserved `.test` is not
    // accepted by the form's email validator). A unique local-part per
    // run avoids the per-email dedup bucket on /api/contact (3/day).
    const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await page
      .getByLabel(/full name/i)
      .fill("Playwright Tester");
    await page
      .getByLabel(/work email/i)
      .fill(`tester+${unique}@mailinator.com`);
    await page
      .getByLabel(/company/i)
      .fill("Voyagent E2E");
    await page
      .getByLabel(/how can we help/i)
      .fill("This is an automated end-to-end test submission.");

    await page.getByRole("button", { name: /send message/i }).click();

    // Assert success only. The per-IP rate limit (5/hour) is loose
    // enough that a single run cannot trip it, and the unique email
    // above keeps the per-email bucket clean.
    await expect(
      page.getByRole("heading", { name: /thanks.*message received/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});
