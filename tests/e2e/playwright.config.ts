import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for the @voyagent/tests-e2e suite.
 *
 * Targets a live deployment (default: https://voyagent.globusdemos.com).
 * Override with VOYAGENT_BASE_URL to point at a different environment.
 *
 * A lightweight global setup pings /api/health so the suite fails fast
 * with a useful message if the target is unreachable.
 */
export default defineConfig({
  testDir: "./specs",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "test-results/junit.xml" }],
  ],
  globalSetup: "./specs/_setup.ts",
  use: {
    baseURL:
      process.env.VOYAGENT_BASE_URL ?? "https://voyagent.globusdemos.com",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: false,
    navigationTimeout: 30_000,
    actionTimeout: 10_000,
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 5"] },
    },
  ],
});
