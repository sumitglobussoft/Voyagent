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
    // fields itself and surfaces a role="alert" div on failure.
    await page.getByRole("button", { name: /send message/i }).click();
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/required/i);
  });

  test("shows success state on valid submit", async ({ page }) => {
    await page
      .getByLabel(/full name/i)
      .fill("Playwright Tester");
    await page.getByLabel(/work email/i).fill("tester@example.com");
    await page
      .getByLabel(/company/i)
      .fill("Voyagent E2E");
    await page
      .getByLabel(/how can we help/i)
      .fill("This is an automated end-to-end test submission.");

    await page.getByRole("button", { name: /send message/i }).click();

    // Success state renders a heading "Thanks — message received."
    const success = page.getByRole("heading", {
      name: /thanks.*message received/i,
    });
    await expect(success).toBeVisible({ timeout: 15_000 });
  });
});
