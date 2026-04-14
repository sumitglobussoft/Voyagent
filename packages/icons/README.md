# @voyagent/icons

Curated icon set for Voyagent. A thin re-export of [lucide-react](https://lucide.dev)
with a deliberately narrow surface.

## Why curated?

Lucide ships well over a thousand icons. Importing directly from
`lucide-react` in each app invites visual drift ("is it `AlarmClock` or
`Clock`?") and — in environments with imperfect tree-shaking — risks
dragging glyphs we never use into the production bundle.

This package:

- exports a vetted list (around two dozen today) that covers the web,
  desktop, and mobile surfaces;
- preserves Lucide's component types (`LucideIcon`, `LucideProps`) so
  consumers get full prop typings;
- gives bundlers an explicit set of named re-exports to tree-shake against.

## Usage

```tsx
import { Plane, Send, Loader2 } from "@voyagent/icons";

<Send size={16} strokeWidth={1.75} aria-hidden="true" />;
```

## Adding an icon

Open `src/index.ts`, find the Lucide PascalCase name (see
https://lucide.dev/icons), and add it to the export list. One-line change,
no other wiring required.

If you find yourself adding a dozen icons for a single feature, surface
it in a design review first — we'd rather grow the curated list
intentionally than drift into "just import whatever from Lucide directly."

## Scripts

- `pnpm --filter @voyagent/icons build`
- `pnpm --filter @voyagent/icons lint`
- `pnpm --filter @voyagent/icons clean`
