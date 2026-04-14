// Voyagent shared Prettier config.
//
// IMPORTANT: This MUST stay byte-for-byte equivalent to the repo root
// `.prettierrc.json`. Keep them in sync — any drift will produce confusing
// diffs when formatting runs from either location.

/** @type {import("prettier").Config} */
const config = {
  printWidth: 100,
  singleQuote: false,
  trailingComma: "all",
  semi: true,
};

export default config;
