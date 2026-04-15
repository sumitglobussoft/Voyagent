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
    body: "The agent extracts sector, dates, passenger types, airline and hotel preferences, budget, and visa need. Anything missing is asked back in natural language — no 10-field form. Live today.",
    variant: "chat" as const,
  },
  {
    title: "2. The quote",
    lede: "Voyagent runs fare search and PNR creation against the Amadeus self-service sandbox and hotel search + price re-check against TBO, assembling a costed quotation — fare rules, inclusions and exclusions all captured.",
    body: "The quote is a canonical Quotation object, not a PDF guess. Revisions (date swap, hotel change, room upgrade) regenerate from the same record without re-keying. Live today, against sandbox endpoints.",
    variant: "quote" as const,
  },
  {
    title: "3. The approval",
    lede: "Aarti sends the quote to the client. On approval, Voyagent re-checks availability and surfaces the booking call with a side-effect + irreversible flag. A senior agent confirms before anything with real-world consequences runs.",
    body: "The approvals inbox, the RBAC scoping, and the audit-log capture of actor / inputs / outputs / approval trail are live today. The issue_ticket call itself is blocked on Amadeus enterprise-tier credentials; TBO booking is blocked on sandbox credentials.",
    variant: "approval" as const,
  },
  {
    title: "4. The booking & delivery",
    lede: "When the booking call unblocks, the ticket issues on the GDS and a Voucher is generated for the hotel. The client receives the itinerary and visa copy in one message.",
    body: "The booking state machine, the Voucher model and the canonical post-sale events (schedule changes, web check-in, visa status polls) are scaffolded. End-to-end delivery depends on real delivery channels — email delivery is on the Shipping-next list, not live.",
    variant: "reconciliation" as const,
  },
  {
    title: "5. The invoice & the books",
    lede: "Receivables and payables are live today — /reports/receivables and /reports/payables age every open invoice and bill into 0-30 / 31-60 / 61-90 / 90+ buckets. Journal posting runs through the accounting agent, with the debit==credit invariant enforced in code.",
    body: "The Tally driver's XML protocol layer — list_accounts, post_journal, create_invoice — is built. The final round-trip to a real Tally instance over :9000 via the Tauri desktop bridge is in progress, not shipped.",
    variant: "reconciliation" as const,
  },
  {
    title: "6. The BSP reconciliation",
    lede: "Voyagent parses BSP India HAF files today, with a 164-airline IATA allow-list. Ticket-sale, refund and cancellation rows come through as canonical records ready for reconciliation.",
    body: "The BSP settlement posting workflow — matching to internal sales, flagging ADM / ACM candidates, booking commission income and remitting net payable — is on the Shipping-next list, not live.",
    variant: "bsp-match" as const,
  },
];

const AT_LAUNCH = [
  "Real-time agentic chat",
  "Approvals inbox for finance overrides",
  "Enquiries CRUD with promote-to-chat",
  "Receivables / payables aging",
  "Hotel search + price-check (TBO)",
  "Multi-tenant isolation",
  "Native deployment on a single Ubuntu host",
];

const SHIPPING_NEXT = [
  "Hotel booking (TBO sandbox creds)",
  "Real ticket issuance (Amadeus production creds)",
  "Tally desktop bridge (real instance)",
  "VFS portal automation (per-tenant selectors)",
  "Real email delivery",
  "Hotelbeds as a second hotel vendor",
];

export default function ProductPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Product walkthrough"
            title="One chat from enquiry to reconciliation — with honest edges."
            description="Follow Aarti — a senior agent at a mid-sized Mumbai agency — through the day as Voyagent runs on main today. Every step is a real canonical object; every action is a tool call; every side-effect is a logged approval. Where we're gated on credentials or an instance we say so, in the step body itself."
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

        <div className="grid gap-6 md:grid-cols-2">
          <article className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-7">
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              At launch — live today
            </h2>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              {AT_LAUNCH.map((item) => (
                <li key={item} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-500"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
          <article className="rounded-2xl border border-amber-200 bg-amber-50/40 p-7">
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Shipping next, in priority order
            </h2>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              {SHIPPING_NEXT.map((item) => (
                <li key={item} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
        </div>
      </div>

      <CtaBand />
    </>
  );
}
