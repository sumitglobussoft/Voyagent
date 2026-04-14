import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Voyagent is in early access. Pricing is tenant-sized and includes setup and white-glove onboarding — contact us for a fit assessment.",
  alternates: { canonical: absoluteUrl("/pricing") },
};

export default function PricingPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Pricing"
            title="Early access. White-glove onboarding. Transparent conversations."
            description="We haven't published a price list yet — and we won't until it's honest. Every early-access tenant gets a tenant-sized quote and a setup engagement that includes driver configuration, data migration, and approval-policy design."
          />
        </div>
      </section>

      <div className="mx-auto w-full max-w-shell px-5 py-16 md:px-8 md:py-24">
        <div className="rounded-2xl border border-primary-100 bg-white p-10 shadow-soft-lg">
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900 md:text-3xl">
            What you can expect today
          </h2>
          <ul className="mt-6 space-y-3 text-base leading-relaxed text-slate-700">
            <li className="flex gap-3">
              <span
                aria-hidden="true"
                className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent"
              />
              <span>
                A fit assessment call — no obligation — to see whether
                Voyagent's current driver coverage matches your stack.
              </span>
            </li>
            <li className="flex gap-3">
              <span
                aria-hidden="true"
                className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent"
              />
              <span>
                A setup engagement if we proceed: driver configuration for
                your GDS, accounting, portals, and payment rails; data
                migration; approval-policy design; training.
              </span>
            </li>
            <li className="flex gap-3">
              <span
                aria-hidden="true"
                className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent"
              />
              <span>
                A tenant-sized subscription after go-live, priced against
                the scope of agents and drivers you actually use.
              </span>
            </li>
          </ul>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/contact"
              className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-base font-semibold text-white shadow-soft-md transition hover:bg-primary-600"
            >
              Contact us
            </Link>
            <Link
              href="/product"
              className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-6 py-3 text-base font-semibold text-slate-800 transition hover:border-primary hover:text-primary"
            >
              See the product walkthrough
            </Link>
          </div>
        </div>
      </div>

      <CtaBand />
    </>
  );
}
