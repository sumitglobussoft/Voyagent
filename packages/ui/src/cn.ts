/**
 * Small className joiner. No dependency on `clsx` — the primitives we ship
 * here have simple conditional-class needs, and a 15-line helper keeps the
 * package runtime-dependency-free.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  const out: string[] = [];
  for (const p of parts) {
    if (typeof p === "string" && p.length > 0) out.push(p);
  }
  return out.join(" ");
}
