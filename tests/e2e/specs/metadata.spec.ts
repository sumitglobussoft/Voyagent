// Covers Next.js metadata routes and the landing-page head tags.

import { expect, test } from "@playwright/test";

test.describe("metadata routes", () => {
  test("/robots.txt is served as text/plain", async ({ request }) => {
    const res = await request.get("/robots.txt");
    expect(res.status()).toBe(200);
    const ct = res.headers()["content-type"] ?? "";
    expect(ct).toMatch(/text\/plain/i);
    const body = await res.text();
    expect(body).toMatch(/User-agent/i);
  });

  test("/sitemap.xml is served as XML and includes the landing URL", async ({
    request,
  }) => {
    const res = await request.get("/sitemap.xml");
    expect(res.status()).toBe(200);
    const ct = res.headers()["content-type"] ?? "";
    expect(ct).toMatch(/xml/i);
    const body = await res.text();
    expect(body).toMatch(/<urlset[\s\S]*<\/urlset>/);
    expect(body).toMatch(/voyagent\.globusdemos\.com/i);
  });

  test("landing page head has description, OG tags, and canonical", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator('meta[name="description"]')).toHaveCount(1);
    await expect(page.locator('link[rel="canonical"]')).toHaveCount(1);
    // OpenGraph — Next auto-generates at least og:title when metadata is set.
    const ogCount = await page.locator('meta[property^="og:"]').count();
    expect(ogCount).toBeGreaterThan(0);
  });
});
