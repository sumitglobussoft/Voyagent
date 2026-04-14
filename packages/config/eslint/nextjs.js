// Voyagent Next.js ESLint config (flat config compatible).
//
// Bridges the legacy `eslint-config-next` shareable config into flat-config form
// using `FlatCompat`. This is the canonical upgrade path recommended by Next.js
// and ESLint until `eslint-config-next` ships a native flat config.

import { FlatCompat } from "@eslint/eslintrc";
import base from "./base.js";

const compat = new FlatCompat({
  baseDirectory: import.meta.dirname,
});

/** @type {import("eslint").Linter.Config[]} */
export default [
  ...base,
  ...compat.extends("next/core-web-vitals"),
];
