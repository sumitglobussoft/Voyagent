// Covers the three domain deep-dive pages under /domains/*.
//
// For each: a top-level heading visibly reflecting the domain name,
// at least one Illustrative-labeled ScreenshotMock, and a CTA band
// that links to /contact.

import { expect, test } from "@playwright/test";

const DOMAINS = [
  {
    path: "/domains/ticketing-visa",
    headingRegex: /ticketing|issuance|gds|visa/i,
  },
  {
    path: "/domains/hotels-holidays",
    headingRegex: /hotel|holiday|package|supplier/i,
  },
  {
    path: "/domains/accounting",
    headingRegex: /account|invoice|ledger|reconcil/i,
  },
] as const;

test.describe("domain pages", () => {
  for (const domain of DOMAINS) {
    test(`${domain.path} renders correctly`, async ({ page }) => {
      const response = await page.goto(domain.path);
      expect(response?.status()).toBeLessThan(400);

      // Top-level heading (rendered as H2 by SectionHeader on these pages)
      const heading = page
        .getByRole("heading")
        .filter({ hasText: domain.headingRegex })
        .first();
      await expect(heading).toBeVisible();

      // At least one ScreenshotMock with the Illustrative label
      await expect(page.getByText(/illustrative/i).first()).toBeVisible();

      // CtaBand links to /contact
      const contactLink = page
        .locator('a[href="/contact"]')
        .first();
      await expect(contactLink).toBeVisible();
    });
  }
});
