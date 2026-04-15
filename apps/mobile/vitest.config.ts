import { defineConfig } from "vitest/config";

// Vitest config scoped narrowly to the Node-testable parts of the
// mobile app. The OCR helper is pure TypeScript and does not import
// React Native, so it runs in Node without a Metro bundler. If we ever
// add React Native component tests, they will need a separate runner
// (jest-expo) rather than extending this config.
export default defineConfig({
  test: {
    environment: "node",
    include: ["__tests__/**/*.test.ts"],
    // Explicitly exclude anything that touches RN / Expo at import time.
    exclude: ["**/node_modules/**", "**/*.tsx"],
  },
});
