import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { MDXRemote } from "next-mdx-remote/rsc";

import { SectionHeader } from "@/components/SectionHeader";
import { isValidSlug, readDoc } from "@/lib/docs";
import {
  DOC_SLUGS,
  DOC_TITLES,
  SITE,
  type DocSlug,
  absoluteUrl,
} from "@/lib/site";

/**
 * Static params for the five in-repo docs. `dynamicParams=false` guards
 * against visitors fabricating slugs that we'd otherwise try to read from
 * disk at request time.
 */
export const dynamicParams = false;

export function generateStaticParams(): Array<{ slug: DocSlug }> {
  return DOC_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  if (!isValidSlug(slug)) return { title: "Docs" };
  const title = DOC_TITLES[slug];
  return {
    title: `${title} — Docs`,
    description: `${SITE.name} ${title.toLowerCase()} document, rendered from the canonical repo source.`,
    alternates: { canonical: absoluteUrl(`/docs/${slug}`) },
  };
}

export default async function DocPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  if (!isValidSlug(slug)) notFound();
  const source = await readDoc(slug);

  return (
    <section className="mx-auto w-full max-w-shell px-5 py-14 md:px-8 md:py-20">
      <div className="mb-10">
        <SectionHeader
          eyebrow="Docs"
          title={DOC_TITLES[slug]}
          description="Rendered from the canonical source in the Voyagent repo. This is the exact document the engineering team reads."
        />
      </div>
      <div className="grid gap-10 lg:grid-cols-[220px_1fr]">
        <aside
          aria-label="Docs navigation"
          className="lg:sticky lg:top-24 lg:self-start"
        >
          <nav className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Documents
            </div>
            <ul className="flex flex-col gap-1">
              {DOC_SLUGS.map((s) => {
                const active = s === slug;
                return (
                  <li key={s}>
                    <Link
                      href={`/docs/${s}`}
                      aria-current={active ? "page" : undefined}
                      className={
                        active
                          ? "block rounded-md bg-primary-50 px-3 py-2 text-sm font-semibold text-primary"
                          : "block rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                      }
                    >
                      {DOC_TITLES[s]}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>
        <article className="doc-prose max-w-none">
          <MDXRemote source={source} />
        </article>
      </div>
    </section>
  );
}
