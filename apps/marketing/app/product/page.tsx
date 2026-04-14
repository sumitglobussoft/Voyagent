import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Product",
  description:
    "A day in the life of Voyagent: one chat drives enquiry, quote, booking, invoice and BSP reconciliation end-to-end.",
  alternates: { canonical: absoluteUrl("/product") },
};

const STEPS = [
  {
    title: "1. The enquiry",
    lede: "Aarti, a senior agent, pastes a WhatsApp forward into chat. The orchestrator classifies it as a ticketing + hotel package enquiry and spins up a structured Enquiry record.",
    body: "The agent extracts sector, dates, passenger types, airline and hotel preferences, budget, and visa need. Anything missing is asked back in natural language — no 10-field form.",
    variant: "chat" as const,
  },
  {
    title: "2. The quote",
    lede: "Voyagent searches fares across Amadeus, pings Hotelbeds for hotel availability, checks UAE e-visa eligibility, and assembles a costed quotation — fare rules, inclusions and exclusions all captured.",
    body: "The quote is a canonical Quotation object, not a PDF guess. Revisions (date swap, hotel change, room upgrade) regenerate from the same record without re-keying.",
    variant: "quote" as const,
  },
  {
    title: "3. The approval",
    lede: "Aarti sends the quote to the client. On approval, Voyagent re-checks availability, holds the PNR, and surfaces the issue_ticket call with a side-effect + irreversible flag.",
    body: "Senior agents see fare, tour code, commission, and the exact time limit. One click issues the ticket; the audit log captures actor, inputs, outputs, and the approval trail.",
    variant: "approval" as const,
  },
  {
    title: "4. The booking & delivery",
    lede: "Ticket issues on the GDS. A Voucher is generated for the hotel. The client gets the itinerary, visa copy and boarding-pass link in one message.",
    body: "The booking state machine tracks post-sale events: schedule changes pushed to the client, web check-in at T-48, visa status polled from the portal.",
    variant: "reconciliation" as const,
  },
  {
    title: "5. The invoice",
    lede: "An Invoice is posted into your accounting system — Tally today, Zoho Books / Busy / QuickBooks on the roadmap — with GST components split correctly.",
    body: "Collections ride UPI, card, NEFT, or payment links. Receipts reconcile against the invoice automatically. Margin and profit per booking compute in real time.",
    variant: "reconciliation" as const,
  },
  {
    title: "6. The BSP reconciliation",
    lede: "On the BSP fortnight, Voyagent pulls BSPlink India, matches ticket sales, refunds and cancellations to internal records, and flags ADM / ACM candidates with evidence attached.",
    body: "A senior agent approves the ACM draft. Commission income books. Net payable remits before the deadline. The books are audit-ready, not AI-flavored.",
    variant: "bsp-match" as const,
  },
];

export default function ProductPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Product walkthrough"
            title="One chat from enquiry to reconciliation."
            description="Follow Aarti — a senior agent at a mid-sized Mumbai agency — through one day of work with Voyagent. Every step is a real canonical object, every action a tool call, every side-effect a logged approval."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-20 px-5 py-20 md:px-8 md:py-28">
        {STEPS.map((step, idx) => (
          <article
            key={step.title}
            className={`grid items-start gap-10 lg:grid-cols-2 ${
              idx % 2 === 1 ? "lg:[&>*:first-child]:order-2" : ""
            }`}
          >
            <div>
              <h2 className="text-2xl font-bold tracking-tighter text-slate-900 md:text-3xl">
                {step.title}
              </h2>
              <p className="mt-4 text-base leading-relaxed text-slate-700">
                {step.lede}
              </p>
              <p className="mt-3 text-base leading-relaxed text-slate-600">
                {step.body}
              </p>
            </div>
            <ScreenshotMock variant={step.variant} />
          </article>
        ))}
      </div>

      <CtaBand />
    </>
  );
}
