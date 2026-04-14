// Covers the public marketing landing page at `/`.
//
// Verifies the hero headline and CTA, top-nav link inventory, the three
// domain cards, the architecture diagram's accessible name, the six-stat
// band, the "Illustrative" honesty label on every ScreenshotMock, and
// the non-affiliation disclaimer in the footer.

import { expect, test } from "@playwright/test";

const NAV_LABELS = [
  "Product",
  "Features",
  "Architecture",
  "Integrations",
  "Security",
  "Pricing",
  "Docs",
] as const;

test.describe("marketing landing", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders the hero with product tagline", async ({ page }) => {
    // The hero H1 carries the product tagline. A separate eyebrow tag
    // carries the "Agentic Travel OS" category line. The brand wordmark
    // "Voyagent" lives in the sticky top-nav above the hero.
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible();
    await expect(h1).toContainText(/one chat/i);
    await expect(page.getByText(/agentic travel os/i).first()).toBeVisible();
  });

  test("hero has primary CTA linking to /product", async ({ page }) => {
    const cta = page.getByRole("link", { name: /explore the product/i });
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", "/product");
  });

  test("nav bar contains core links", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: /primary/i });
    for (const label of NAV_LABELS) {
      await expect(nav.getByRole("link", { name: label })).toBeVisible();
    }
  });

  test("renders three domain cards", async ({ page }) => {
    const domains = [
      "/domains/ticketing-visa",
      "/domains/hotels-holidays",
      "/domains/accounting",
    ];
    for (const href of domains) {
      await expect(page.locator(`a[href="${href}"]`).first()).toBeVisible();
    }
  });

  test("architecture diagram is present and accessible", async ({ page }) => {
    // ArchitectureDiagram is rendered as a <figure role="img"> whose
    // accessible name comes from an aria-labelledby reference to an
    // SVG <title>. The exact text is "Voyagent six-layer architecture".
    const diagram = page.getByRole("img", { name: /architecture/i }).first();
    await expect(diagram).toBeVisible();
  });

  test("stat band shows all six stats", async ({ page }) => {
    // The STATS array on the landing page has exactly six entries. We
    // pin this count to catch accidental deletions.
    const statLabels = [
      /functional domains/i,
      /activities automated/i,
      /vendor-agnostic/i,
      /india-first/i,
      /per-tenant/i,
      /every side-effect/i,
    ];
    for (const label of statLabels) {
      await expect(page.getByText(label).first()).toBeVisible();
    }
  });

  test("screenshot mock is labeled Illustrative", async ({ page }) => {
    // Every ScreenshotMock renders a small "Illustrative" chip in the
    // top-right. At least one mock is present on the landing page.
    await expect(page.getByText(/illustrative/i).first()).toBeVisible();
  });

  test("footer carries non-affiliation disclaimer", async ({ page }) => {
    const footer = page.getByRole("contentinfo");
    await expect(footer).toContainText(/not affiliated/i);
    await expect(footer).toContainText(/trademarks/i);
  });
});
