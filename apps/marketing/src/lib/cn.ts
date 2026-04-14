/**
 * Lightweight className combiner.
 *
 * Mirrors `@voyagent/ui`'s `cn` but avoids adding a cross-package import
 * (the `ui` package is bundled with its own copy). Accepts strings,
 * numbers, undefined, and nested arrays — drops falsy values.
 */
export function cn(
  ...values: Array<string | number | false | null | undefined>
): string {
  return values.filter(Boolean).join(" ");
}
