import type { Metadata } from "next";

import { ContactForm } from "@/components/ContactForm";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Get in touch with the Voyagent team — early access, partnerships, integration questions.",
  alternates: { canonical: absoluteUrl("/contact") },
};

export default function ContactPage() {
  return (
    <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
      <div className="grid gap-12 lg:grid-cols-2">
        <div>
          <SectionHeader
            eyebrow="Contact"
            title="Tell us about your agency."
            description="We'll reply within one business day. Early-access fit assessments take about 30 minutes and don't come with pressure."
          />
          <div className="mt-8 space-y-4 text-sm text-slate-600">
            <p>
              Prefer email? Write to{" "}
              <a
                href="mailto:hello@voyagent.globusdemos.com"
                className="font-semibold text-primary"
              >
                hello@voyagent.globusdemos.com
              </a>
              .
            </p>
            <p>
              What we&rsquo;ll ask about on a fit call: which GDS(es) you
              use, your accounting stack, your BSP status, any portals that
              matter to you (VFS, BLS, airline extranets), and your current
              team size.
            </p>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-soft-md">
          <ContactForm />
        </div>
      </div>
    </section>
  );
}
