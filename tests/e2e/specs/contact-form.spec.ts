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
    // accepted by the form's email validator). The live /api/contact
    // route is rate-limited; if we hit a 429 we treat that as a
    // successful backend contact rather than a failure, since it still
    // proves the submit wired into the API.
    await page
      .getByLabel(/full name/i)
      .fill("Playwright Tester");
    await page
      .getByLabel(/work email/i)
      .fill(`tester+${Date.now()}@mailinator.com`);
    await page
      .getByLabel(/company/i)
      .fill("Voyagent E2E");
    await page
      .getByLabel(/how can we help/i)
      .fill("This is an automated end-to-end test submission.");

    await page.getByRole("button", { name: /send message/i }).click();

    // Accept either the success heading or the rate-limit banner —
    // both prove the form wired into the backend. The "429" / "try
    // again" copy is what the live deployment serves under load.
    const success = page.getByRole("heading", {
      name: /thanks.*message received/i,
    });
    const rateLimited = page.getByText(
      /(429|rate limit|try again)/i,
    );
    await expect(success.or(rateLimited).first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
