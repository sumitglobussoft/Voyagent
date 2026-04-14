// Very loose performance smoke.
//
// - /  must complete page.goto within 15s (Cloudflare + Asia routing).
// - First Contentful Paint soft-warns if > 4s; it does not fail the run.
// - Every HTML response's content-type includes "text/html".

import { expect, test } from "@playwright/test";

test.describe("performance budget", () => {
  test("landing page loads within 15s and serves text/html", async ({
    page,
  }, testInfo) => {
    const started = Date.now();
    const response = await page.goto("/", { waitUntil: "load" });
    const elapsed = Date.now() - started;

    expect(
      elapsed,
      `page.goto("/") took ${elapsed}ms (budget 15000ms)`,
    ).toBeLessThan(15_000);

    expect(response).not.toBeNull();
    const ct = response!.headers()["content-type"] ?? "";
    expect(ct).toMatch(/text\/html/i);

    const paints = await page.evaluate(() => {
      const entries = performance.getEntriesByType("paint") as Array<
        PerformanceEntry & { startTime: number }
      >;
      const fcp = entries.find((e) => e.name === "first-contentful-paint");
      return fcp ? fcp.startTime : null;
    });

    if (paints !== null) {
      testInfo.annotations.push({
        type: "fcp-ms",
        description: `${Math.round(paints)}`,
      });
      if (paints > 4000) {
        testInfo.annotations.push({
          type: "fcp-warning",
          description: `FCP ${Math.round(paints)}ms exceeds soft budget 4000ms`,
        });
      }
    }
  });

  test("subpages serve text/html", async ({ request }) => {
    const paths = ["/product", "/features", "/architecture", "/docs/STACK"];
    for (const path of paths) {
      const res = await request.get(path, { maxRedirects: 5 });
      expect(res.status()).toBeLessThan(400);
      const ct = res.headers()["content-type"] ?? "";
      expect(ct, `content-type for ${path}`).toMatch(/text\/html/i);
    }
  });
});
