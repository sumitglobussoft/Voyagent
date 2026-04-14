# @voyagent/ui

Primitive React components for Voyagent's web and desktop surfaces.

This package ships small, accessible, ref-forwarding building blocks:
`Button`, `Input`, `TextArea`, `Card`, `EmptyState`, `Spinner`, `Badge`,
`Stack`, and `Avatar`. Every component is a single file under `src/` and
has zero runtime dependencies outside `react` / `react-dom`.

## What's in the box

| Component    | Purpose                                                           |
| ------------ | ----------------------------------------------------------------- |
| `Button`     | Primary / secondary / ghost, with `loading` spinner + `aria-busy` |
| `Input`      | Text input with `label`, `description`, `error`, `required`       |
| `TextArea`   | Multi-line input with auto-grow up to a configurable `maxHeight`  |
| `Card`       | Container with optional `header` and `footer` slots               |
| `EmptyState` | Icon + title + description + optional CTA placeholder             |
| `Spinner`    | Indeterminate CSS spinner (uses Tailwind's `animate-spin`)        |
| `Badge`      | Neutral / info / success / warning / danger pill                  |
| `Stack`      | Flex wrapper with `direction`, `gap`, `align`, `justify`, `wrap`  |
| `Avatar`     | Image with initials fallback on load error                        |

## Install

This package is workspace-only:

```json
{
  "dependencies": {
    "@voyagent/ui": "workspace:*"
  }
}
```

## Usage

```tsx
import { Button, Card, Stack } from "@voyagent/ui";

export function Example() {
  return (
    <Card header="Pending approvals">
      <Stack gap="sm">
        <p>One approval needed to proceed.</p>
        <Button variant="primary">Review</Button>
      </Stack>
    </Card>
  );
}
```

## Tailwind prerequisite

The components emit Tailwind utility classes (`rounded-md`, `bg-neutral-900`,
`animate-spin`, etc.). Consumers must:

1. Have Tailwind CSS v3+ installed and configured in the host app.
2. Include the `@voyagent/ui` source in their Tailwind `content` glob so
   the utilities used here survive the JIT purge:

   ```js
   // tailwind.config.js
   export default {
     content: [
       "./app/**/*.{ts,tsx}",
       "./components/**/*.{ts,tsx}",
       "../../packages/ui/src/**/*.{ts,tsx}",
     ],
   };
   ```

The shared `@voyagent/config/tailwind/preset` already bundles the color
and spacing scales we rely on.

## Accessibility

- `Button` sets `aria-busy` while loading and keeps the button disabled
  so double-submits can't happen.
- `Input` and `TextArea` wire `label` / `htmlFor` via `useId`, attach
  `aria-describedby` for description + error text, and flip
  `aria-invalid` on error.
- `Spinner` wraps its animation in `role="status"` with `aria-live="polite"`
  and an `sr-only` label (defaults to "Loading").
- `EmptyState` is a `status` region; provide a clear `title` for screen
  readers.
- `Avatar` falls back to initials with `aria-label` so screen readers
  still announce the person when the image is missing.

## Scripts

- `pnpm --filter @voyagent/ui build`
- `pnpm --filter @voyagent/ui lint` (type-checks with `tsc --noEmit`)
- `pnpm --filter @voyagent/ui clean`

## Scope

Primitives only. Anything agent-specific (chat bubbles, approval prompts,
tool-call cards) belongs in `@voyagent/chat`. Anything domain-specific
(itinerary cards, invoice rows) is scoped to the consuming app.
