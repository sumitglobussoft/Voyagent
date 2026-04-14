# @voyagent/config

Shared build configuration for every Voyagent surface (Web, Desktop, Mobile).
This package is the **only** place where cross-app TS / ESLint / Tailwind /
Prettier / Tamagui token config lives. Apps extend from here so configs never
drift.

> Change anything in this package and you change every app. Tread carefully.

## What's in the box

- `tsconfig/base.json` — strict ES2022 NodeNext baseline.
- `tsconfig/nextjs.json` — Next.js app (jsx preserve, Bundler resolution).
- `tsconfig/react-library.json` — `.d.ts`-emitting library preset.
- `eslint/base.js` — ESLint v9 flat config with `@typescript-eslint`.
- `eslint/nextjs.js` — flat config + `eslint-config-next` via `FlatCompat`.
- `tailwind/preset.js` — brand colors + `Inter` sans stack.
- `prettier/index.js` — mirrors the repo root `.prettierrc.json`.
- `tamagui/tokens.js` — stub tokens for the native surface.

## How to use

### TypeScript

```json
// apps/web/tsconfig.json
{
  "extends": "@voyagent/config/tsconfig/nextjs.json",
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"]
}
```

### ESLint (flat config)

```js
// apps/web/eslint.config.js
import nextjs from "@voyagent/config/eslint/nextjs";
export default [...nextjs];
```

### Tailwind

```js
// apps/web/tailwind.config.js
import preset from "@voyagent/config/tailwind/preset";

export default {
  presets: [preset],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
};
```

### Prettier

```js
// prettier.config.js
export { default } from "@voyagent/config/prettier";
```

## Conventions

- ESM only (`"type": "module"`).
- No hand-written `any` downstream — `@typescript-eslint/no-explicit-any` is an
  error in the base ESLint preset.
- Strict TS with `noUncheckedIndexedAccess`. If you index into an array, handle
  `undefined`.
