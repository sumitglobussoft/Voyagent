import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "About",
  description:
    "About Voyagent — a small team building the Agentic Travel OS for travel agencies worldwide, starting in India.",
  alternates: { canonical: absoluteUrl("/about") },
};

export default function AboutPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="About"
            title="A small team. An adapter-first bet."
            description="Voyagent is built by a small team that has spent a long time watching travel agencies juggle eight to fifteen tools a day. We think the 'AI for travel' headline is the easy part — the adapter layer is the hard one, and it's the one we're building first."
          />
        </div>
      </section>

      <div className="mx-auto grid w-full max-w-shell gap-10 px-5 py-16 md:grid-cols-2 md:px-8 md:py-24">
        <article className="prose-body">
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            What we believe
          </h2>
          <p className="mt-4 text-base leading-relaxed text-slate-700">
            Agency ops are well-defined, rule-heavy and highly repeatable —
            ideal territory for AI agents. But the agents only pay off if
            the integration surface actually works: every GDS, every
            accounting system, every payment rail, every visa portal.
          </p>
          <p className="mt-4 text-base leading-relaxed text-slate-700">
            So we&rsquo;re building a canonical domain model, a driver
            layer, and a tool runtime before we scale the agent catalog.
            That&rsquo;s the moat — and it&rsquo;s the reason we&rsquo;ll
            still be a credible platform when the underlying models change
            again next year.
          </p>
        </article>
        <article className="prose-body">
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Where we are
          </h2>
          <p className="mt-4 text-base leading-relaxed text-slate-700">
            Canonical model v0 is in. Amadeus, Tally, BSP India and VFS
            drivers are in varying states between full and partial. The
            first vertical slice — enquiry &rarr; quote &rarr; ticket
            &rarr; invoice &rarr; BSP reconciliation — is the gate we&rsquo;re
            driving toward with our early-access customers.
          </p>
          <p className="mt-4 text-base leading-relaxed text-slate-700">
            We publish our architecture, decision log and activity
            inventory openly — see the{" "}
            <Link
              href="/docs/ARCHITECTURE"
              className="font-semibold text-primary underline"
            >
              docs
            </Link>
            . If you&rsquo;re an agency with strong opinions about Tally,
            BSP, VFS or GDS workflows, we&rsquo;d love to talk.
          </p>
        </article>
      </div>

      <section className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto flex w-full max-w-shell flex-col items-start justify-between gap-6 px-5 py-14 md:flex-row md:items-center md:px-8">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Get in touch
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Questions, integrations, partnerships, early access.
            </p>
          </div>
          <Link
            href="/contact"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-base font-semibold text-white"
          >
            Contact us
          </Link>
        </div>
      </section>

      <CtaBand />
    </>
  );
}
