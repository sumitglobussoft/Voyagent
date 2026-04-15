import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { SITE, absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: `Early access — ${SITE.name}`,
  description:
    "Voyagent is in private early access. Request a workspace and we will onboard your agency with white-glove support.",
  alternates: { canonical: absoluteUrl("/early-access") },
};

/**
 * Sign-in / early-access landing.
 *
 * The authenticated app at `/app` is intentionally gated while the
 * pilot cohort is closed. Sending `Sign in` to this page keeps the CTA
 * honest: self-service sign-up is off, and the fastest path to a real
 * workspace is the contact form.
 */
export default function EarlyAccessPage() {
  return (
    <>
      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="Sign in"
          title="Voyagent is in private early access."
          description="We are onboarding a small cohort of travel agencies hand-in-hand. Self-service sign-up is intentionally off while we wire up tenant-specific credentials, vendor integrations, and compliance controls for each workspace."
          align="center"
        />

        <div className="mx-auto mt-10 max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 shadow-soft-md md:p-12">
          <div className="space-y-6 text-slate-700">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">
                What the pilot looks like
              </h2>
              <ul className="mt-3 space-y-2 text-sm leading-relaxed">
                <li>
                  <span className="font-medium text-slate-900">Week 1.</span>{" "}
                  Kickoff call, activity mapping against your current ops, and
                  an agreed subset of workflows for the first slice.
                </li>
                <li>
                  <span className="font-medium text-slate-900">Week 2.</span>{" "}
                  GDS, accounting and payment-gateway credentials wired into
                  your dedicated tenant — per-tenant encryption, per-tenant
                  audit log.
                </li>
                <li>
                  <span className="font-medium text-slate-900">Week 3.</span>{" "}
                  Your first real chat sessions driving live bookings with a
                  Voyagent engineer on the call.
                </li>
                <li>
                  <span className="font-medium text-slate-900">Week 4+.</span>{" "}
                  Weekly check-ins, reconciliation review, and iterative
                  expansion into the remaining domains.
                </li>
              </ul>
            </div>

            <div className="border-t border-slate-200 pt-6">
              <h2 className="text-lg font-semibold text-slate-900">
                Who we prioritise in the pilot
              </h2>
              <ul className="mt-3 space-y-2 text-sm leading-relaxed">
                <li>
                  Independent travel agencies in India running Amadeus and
                  Tally today. The v0 pilot scope is Amadeus (sandbox) plus
                  Tally&apos;s XML protocol layer; additional GDS and
                  accounting drivers are on the roadmap — see{" "}
                  <Link
                    href="/integrations"
                    className="font-medium text-primary hover:underline"
                  >
                    /integrations
                  </Link>
                  .
                </li>
                <li>
                  Teams that handle the full ticketing + hotel + visa +
                  accounting stack end-to-end (not only one vertical).
                </li>
                <li>
                  An operator-owner or COO who can spend two hours per week
                  with our team during the pilot.
                </li>
              </ul>
            </div>

            <div className="flex flex-col items-start gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-600">
                Ready to talk? We respond within one business day.
              </p>
              <Link
                href="/contact"
                className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-soft-md transition hover:bg-primary-600"
              >
                Request a workspace
              </Link>
            </div>
          </div>
        </div>

        <p className="mx-auto mt-8 max-w-3xl text-center text-xs text-slate-500">
          Already in the pilot? Your team received a direct link to your
          tenant&apos;s workspace at onboarding. The public site does not
          host a self-service sign-in while the cohort is closed.
        </p>
      </section>

      <CtaBand />
    </>
  );
}
