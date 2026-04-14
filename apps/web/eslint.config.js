// Flat-config ESLint entry for @voyagent/web.
//
// The shared Next.js preset at `@voyagent/config/eslint/nextjs` bridges
// `eslint-config-next` into flat-config form via FlatCompat and layers on
// the workspace base rules. We re-export it with a local `ignores` block
// so `eslint .` doesn't descend into build output.
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
