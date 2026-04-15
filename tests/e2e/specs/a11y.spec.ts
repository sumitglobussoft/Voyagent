// WCAG 2.0/2.1 A+AA sweep across every public and authed page.
//
// This complements `accessibility.spec.ts` (which only guards against
// serious/critical regressions on a small set of marketing pages).
// This spec is the _comprehensive_ baseline — one test per route, each
// one asserting `results.violations` is empty.
//
// Philosophy:
//   - When a page has real violations, the corresponding test is marked
//     with `test.fail()` and a TODO listing the offending rules. That
//     turns this file into a live a11y backlog that future UX work can
//     burn down one page at a time.
//   - We run against chromium-desktop only. Mobile a11y is a secondary
//     concern right now and the CI budget is tight.
//
// How to run against the live site:
//   VOYAGENT_BASE_URL=https://voyagent.globusdemos.com \
//     pnpm --filter @voyagent/tests-e2e exec playwright test a11y.spec.ts

import { expect, test as baseTest } from "@playwright/test";

import { test as authedTest } from "../fixtures/authed";
import { runAxe } from "../fixtures/axe";

// chromium-desktop only for v0. Mobile a11y is a secondary concern and
// the CI runtime budget is tight.
function skipIfNotDesktop(testInfo: { project: { name: string } }): void {
  if (testInfo.project.name !== "chromium-desktop") {
    baseTest.skip(true, "a11y sweep runs on chromium-desktop only");
  }
}

// --------------------------------------------------------------------------- //
// Public (unauthenticated) pages                                              //
// --------------------------------------------------------------------------- //

const PUBLIC_ROUTES: ReadonlyArray<{
  path: string;
  /** If set, the test is expected to fail and the reason/rules are the TODO backlog. */
  todo?: string;
}> = [
  { path: "/" },
  { path: "/pricing" },
  { path: "/about" },
  { path: "/contact" },
  { path: "/security" },
  { path: "/features" },
  { path: "/integrations" },
  { path: "/architecture" },
  { path: "/product" },
  { path: "/app/sign-in" },
  { path: "/app/sign-up" },
  { path: "/app/forgot-password" },
];

baseTest.describe("a11y (public)", () => {
  for (const { path, todo } of PUBLIC_ROUTES) {
    const runner = todo ? baseTest.fail : baseTest;
    runner(`${path} has no WCAG A/AA violations`, async ({ page }, testInfo) => {
      skipIfNotDesktop(testInfo);
      const response = await page.goto(path, { waitUntil: "domcontentloaded" });
      // Some routes may redirect or 404 in certain environments; skip those
      // cleanly rather than erroring out so the rest of the sweep runs.
      if (!response || response.status() >= 400) {
        baseTest.skip(true, `${path} returned ${response?.status() ?? "no"} response`);
      }
      const results = await runAxe(page);
      expect(
        results.violations,
        formatViolations(path, results.violations),
      ).toEqual([]);
    });
  }
});

// --------------------------------------------------------------------------- //
// Authed (signed-in) pages                                                    //
// --------------------------------------------------------------------------- //

const AUTHED_ROUTES: ReadonlyArray<{ path: string; todo?: string }> = [
  { path: "/app/chat" },
  { path: "/app/enquiries" },
  { path: "/app/enquiries/new" },
  { path: "/app/approvals" },
  { path: "/app/audit" },
  { path: "/app/profile" },
  { path: "/app/settings" },
];

authedTest.describe("a11y (authed)", () => {
  for (const { path, todo } of AUTHED_ROUTES) {
    const runner = todo ? authedTest.fail : authedTest;
    runner(`${path} has no WCAG A/AA violations`, async ({ authedPage }, testInfo) => {
      skipIfNotDesktop(testInfo);
      const response = await authedPage.goto(path, {
        waitUntil: "domcontentloaded",
      });
      if (!response || response.status() >= 400) {
        authedTest.skip(
          true,
          `${path} returned ${response?.status() ?? "no"} response`,
        );
      }
      const results = await runAxe(authedPage);
      expect(
        results.violations,
        formatViolations(path, results.violations),
      ).toEqual([]);
    });
  }
});

// --------------------------------------------------------------------------- //
// Helpers                                                                     //
// --------------------------------------------------------------------------- //

type AxeViolation = {
  id: string;
  impact?: string | null;
  help: string;
  nodes: Array<unknown>;
};

function formatViolations(path: string, violations: AxeViolation[]): string {
  if (violations.length === 0) return `no violations on ${path}`;
  const lines = violations.map(
    (v) => `  - [${v.impact ?? "minor"}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`,
  );
  return `WCAG A/AA violations on ${path}:\n${lines.join("\n")}`;
}
