/**
 * Vitest configuration for @voyagent/ui.
 *
 * Uses JSDOM (components are DOM-first) and auto-imports the RTL
 * jest-dom matchers via `setupFiles`. Tests live under `src/__tests__`.
 */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/__tests__/**/*.test.ts?(x)"],
  },
});
