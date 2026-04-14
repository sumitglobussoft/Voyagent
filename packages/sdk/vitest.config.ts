/**
 * Vitest configuration for @voyagent/sdk.
 *
 * Runs in Node — the SDK is runtime-agnostic but its tests only exercise
 * the fetch / streams layer, which Node 20+ ships natively. No JSDOM.
 */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["tests/**/*.test.ts"],
  },
});
