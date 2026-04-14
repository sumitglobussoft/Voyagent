import type { Metadata } from "next";
import Link from "next/link";
import {
  Plane,
  Hotel,
  Calculator,
  FileText,
  Receipt,
  CreditCard,
} from "@voyagent/icons";

import { ArchitectureDiagram } from "@/components/ArchitectureDiagram";
import { CtaBand } from "@/components/CtaBand";
import { DomainCard } from "@/components/DomainCard";
import { Hero } from "@/components/Hero";
import { LogoMarquee } from "@/components/LogoMarquee";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { StatBadge } from "@/components/StatBadge";
import { TestimonialPlaceholder } from "@/components/TestimonialPlaceholder";
import { SITE, absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: `${SITE.name} — ${SITE.category}`,
  description: SITE.description,
  alternates: { canonical: absoluteUrl("/") },
};

const STATS = [
  { value: "3", label: "Functional domains covered" },
  { value: "100+", label: "Activities automated" },
  { value: "Vendor-agnostic", label: "By architecture, not by roadmap" },
  { value: "India-first", label: "Global-ready from day one" },
  { value: "Per-tenant", label: "Credential & data isolation" },
  { value: "Every side-effect", label: "Audited with approval trail" },
];

export default function LandingPage() {
  return (
    <>
      <Hero />

      <section className="border-b border-slate-200">
        <div className="mx-auto w-full max-w-shell px-5 py-6 text-center md:px-8">
          <div className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-500">
            Built to integrate with
          </div>
        </div>
        <LogoMarquee />
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="Three domains, one chat"
          title="Replaces the full travel-agency ops stack."
          description="Voyagent is not a copilot bolted onto an existing tool. It is the chat interface and the workflow engine — driving the GDS, the visa portal, and the accounting system end-to-end."
        />
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          <DomainCard
            title="Ticketing & Visa"
            summary="Enquiry to issuance to web check-in, across every GDS, consolidator and visa portal."
            href="/domains/ticketing-visa"
            icon={Plane}
            bullets={[
              "Fare search across GDS + consolidators",
              "PNR creation, queues, ticket issuance",
              "Visa checklist, form-fill, appointment, tracking",
              "Schedule change and refund handling",
            ]}
          />
          <DomainCard
            title="Hotels & Holidays"
            summary="Package building from multiple suppliers — hotels, land, transport, tours, Umrah — with costing and vouchers."
            href="/domains/hotels-holidays"
            icon={Hotel}
            bullets={[
              "Multi-supplier rate aggregation",
              "Package costing + quotation",
              "Voucher issuance and revisions",
              "Post-booking support and reconciliation",
            ]}
          />
          <DomainCard
            title="Accounting"
            summary="Invoices, collections, supplier payments, BSP reconciliation, GST and TDS — posted into the accounting system you already use."
            href="/domains/accounting"
            icon={Calculator}
            bullets={[
              "Invoicing + receipts in Tally / Zoho / Busy",
              "BSP / card / bank reconciliation",
              "GST and TDS compute and file",
              "Audit-ready books, per-booking profit",
            ]}
          />
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
          <SectionHeader
            eyebrow="Three capability tiers"
            title="Identify &amp; Collect. Verify. Act."
            description="Every activity lives on this spine. AI agents handle the first two freely; irreversible Act steps are gated behind explicit human approval."
          />
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {[
              {
                tier: "1. Identify & Collect",
                icon: FileText,
                copy: "Structured intake of requirements, documents, and client context via chat. No more 8-tab data entry.",
              },
              {
                tier: "2. Verify",
                icon: Receipt,
                copy: "Rule-based + LLM verification: passport validity, document completeness, fare legality, reconciliation matches.",
              },
              {
                tier: "3. Act",
                icon: CreditCard,
                copy: "Side-effecting tools — issue tickets, post journal entries, submit visa applications, disburse payments. Gated, logged, reversible where possible.",
              },
            ].map((t) => {
              const Icon = t.icon;
              return (
                <div
                  key={t.tier}
                  className="rounded-xl border border-slate-200 bg-white p-6 shadow-soft-md"
                >
                  <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary">
                    <Icon width={20} height={20} aria-hidden="true" />
                  </div>
                  <div className="text-lg font-semibold text-slate-900">
                    {t.tier}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    {t.copy}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="Scope, honestly"
          title="Where we stand."
          description="Numbers we'll stand behind. We're early access — no usage metrics fabricated here."
          align="center"
        />
        <div className="mt-10 grid gap-4 md:grid-cols-3 lg:grid-cols-6">
          {STATS.map((s) => (
            <StatBadge key={s.label} value={s.value} label={s.label} />
          ))}
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto grid w-full max-w-shell gap-10 px-5 py-20 md:grid-cols-2 md:px-8 md:py-28">
          <div>
            <SectionHeader
              eyebrow="Under the hood"
              title="An adapter-first architecture."
              description="The AI is not the hard part. The adapter layer is. Voyagent is a canonical domain model with drivers per vendor, agents on top, and platform services underneath."
            />
            <div className="mt-8 flex gap-3">
              <Link
                href="/architecture"
                className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-600"
              >
                Read the architecture
              </Link>
              <Link
                href="/docs/ARCHITECTURE"
                className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 transition hover:border-primary hover:text-primary"
              >
                Open doc
              </Link>
            </div>
          </div>
          <ArchitectureDiagram compact />
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="A real flow"
          title='"Quote a Dubai 4-night Emirates direct for 2 adults."'
          description="One chat. Fare search across Amadeus, hotel rates via Hotelbeds, visa eligibility check, bundled quotation — no tab switching."
        />
        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <ScreenshotMock variant="chat" />
          <ScreenshotMock variant="quote" />
        </div>
      </section>

      <TestimonialPlaceholder />
      <CtaBand />
    </>
  );
}
