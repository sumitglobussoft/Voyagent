import fs from "node:fs/promises";
import path from "node:path";

import { DOC_SLUGS, type DocSlug } from "./site";

/**
 * Docs I/O helpers.
 *
 * ### How /docs consumes the repo's Markdown
 * The marketing app reads `docs/*.md` from the monorepo root at request
 * time via `fs/promises`. At build-time `generateStaticParams()` produces
 * the five concrete slugs so each doc gets its own pre-rendered HTML.
 *
 * The path is resolved relative to `process.cwd()` which, for a Next.js
 * standalone build, points at the `apps/marketing` directory. We walk two
 * levels up to reach the repo's `docs/` folder. For the production
 * systemd deployment (migrated off Docker 2026-04-14), the deploy script
 * rsyncs `docs/` next to the standalone server output, so the second and
 * third candidates below resolve against that sibling directory.
 */
const DOCS_DIR_CANDIDATES = [
  // running from apps/marketing at dev time
  path.resolve(process.cwd(), "..", "..", "docs"),
  // running from repo root
  path.resolve(process.cwd(), "docs"),
  // standalone bundle sibling (systemd deploy rsyncs docs next to the
  // standalone server)
  path.resolve(process.cwd(), "docs"),
];

export function isValidSlug(slug: string): slug is DocSlug {
  return (DOC_SLUGS as readonly string[]).includes(slug);
}

export async function readDoc(slug: DocSlug): Promise<string> {
  const filename = `${slug}.md`;
  const errors: string[] = [];
  for (const base of DOCS_DIR_CANDIDATES) {
    const full = path.join(base, filename);
    try {
      return await fs.readFile(full, "utf-8");
    } catch (err) {
      errors.push(`${full}: ${(err as Error).message}`);
    }
  }
  throw new Error(
    `Could not locate doc '${slug}'. Tried:\n${errors.join("\n")}`,
  );
}
