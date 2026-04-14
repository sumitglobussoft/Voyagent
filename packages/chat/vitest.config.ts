/**
 * Vitest configuration for @voyagent/chat.
 *
 * JSDOM environment because the tested components render into the DOM
 * (`*.web.tsx`). The React Native entries (`*.native.tsx`) are out of
 * scope here — they need a Metro-like runtime and are covered by the
 * mobile app's integration tests.
 */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts?(x)"],
  },
});
