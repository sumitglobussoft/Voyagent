// Flat-config ESLint entry for @voyagent/marketing.
//
// Mirrors `apps/web/eslint.config.js` so both Next.js apps lint identically.
import nextPreset from "@voyagent/config/eslint/nextjs";

/** @type {import("eslint").Linter.Config[]} */
export default [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "dist/**",
      "next-env.d.ts",
      "*.tsbuildinfo",
    ],
  },
  ...nextPreset,
];
