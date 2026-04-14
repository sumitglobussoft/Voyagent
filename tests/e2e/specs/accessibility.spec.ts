// Accessibility audits via axe-core.
//
// Runs on a representative set of public pages. Fails only on violations
// whose impact is "serious" or "critical". Lower-severity findings are
// captured as test annotations so they show up in the HTML report but
// don't break the build.

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const TARGETS = [
  "/",
  "/product",
  "/features",
  "/architecture",
  "/docs/ARCHITECTURE",
] as const;

test.describe("accessibility", () => {
  for (const path of TARGETS) {
    test(`${path} has no serious or critical a11y violations`, async ({
      page,
    }, testInfo) => {
      await page.goto(path);

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const blocking = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      const softer = results.violations.filter(
        (v) => v.impact !== "serious" && v.impact !== "critical",
      );

      for (const v of softer) {
        testInfo.annotations.push({
          type: `a11y-${v.impact ?? "minor"}`,
          description: `${v.id}: ${v.help} (${v.nodes.length} nodes)`,
        });
      }

      expect(
        blocking,
        `serious/critical a11y violations on ${path}:\n` +
          blocking
            .map(
              (v) =>
                `  - [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`,
            )
            .join("\n"),
      ).toEqual([]);
    });
  }
});
