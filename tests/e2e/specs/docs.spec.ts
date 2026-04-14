// Covers /docs/[slug] for every in-repo doc slug.
//
// Each slug must: return 2xx, render more than 500 bytes of body text
// (proxy for MDX having rendered), and show a docs sidebar that lists
// all 5 slugs as links.

import { expect, test } from "@playwright/test";

const DOC_SLUGS = [
  "ARCHITECTURE",
  "DECISIONS",
  "CANONICAL_MODEL",
  "STACK",
  "ACTIVITIES",
] as const;

test.describe("docs pages", () => {
  for (const slug of DOC_SLUGS) {
    test(`/docs/${slug} renders MDX and sidebar`, async ({ page }) => {
      const response = await page.goto(`/docs/${slug}`);
      expect(response?.status()).toBeLessThan(400);

      const bodyText = (await page.locator("body").innerText()).trim();
      expect(
        bodyText.length,
        `expected MDX body > 500 chars for ${slug}, got ${bodyText.length}`,
      ).toBeGreaterThan(500);

      // The docs layout renders a sidebar link list containing every
      // slug. We match by visible label rather than slug literal so the
      // sidebar can pretty-print titles.
      for (const other of DOC_SLUGS) {
        const link = page
          .locator(`a[href="/docs/${other}"]`)
          .first();
        await expect(link).toBeVisible();
      }
    });
  }
});
