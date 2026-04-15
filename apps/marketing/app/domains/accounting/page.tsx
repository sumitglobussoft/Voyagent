import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Accounting & Finance",
  description:
    "Chat-driven journal posting via the accounting agent, double-entry invariant enforced in code, receivables / payables aging, and a Tally XML protocol layer. Desktop bridge to a real Tally instance is in progress.",
  alternates: { canonical: absoluteUrl("/domains/accounting") },
};

const LIVE_TODAY = [
  "Chat-driven journal posting via the accounting agent",
  "Double-entry journal_entries table with the debit==credit invariant enforced in code",
  "invoices and bills tables with /reports/receivables and /reports/payables aging buckets (0-30 / 31-60 / 61-90 / 90+)",
  "Tally driver XML protocol layer — list_accounts, post_journal, create_invoice request shapes",
];

const SHIPPING_NEXT = [
  "End-to-end Tally XML-over-:9000 round-trip via the Tauri desktop bridge (blocked on a real Tally instance)",
  "BSP India settlement posting workflow",
  "Zoho Books, Busy, QuickBooks, SAP and Marg as additional accounting drivers",
];

const ACTIVITIES = [
  "Create invoices, send to clients, maintain billing records, prepare and share statements",
  "Follow up for collections, record customer payments, issue receipts",
  "Handle collections via UPI, bank transfer, card, cash and payment links",
  "Generate and send payment links by email, SMS or other channels",
  "Process supplier invoices and payments (NEFT, RTGS, cheque, card)",
  "Prepare challans, submit banking documents, handle urgent credit-card payments",
  "Process VFS or vendor payment links",
  "Record ticket, hotel, visa and service costs; update accounting software",
  "Pass journal vouchers, update commission entries, prepare incentive billings",
  "Handle cash receipts, count cash, update cash transactions",
  "Reconcile vendor, customer, supplier, bank, card, and payment-gateway statements",
  "Track credit-card utilization, failed transactions, duplicate charges and chargebacks",
  "Reconcile BSP statements with internal sales; check fares, refunds, cancellations",
  "Raise ADM / ACM queries and make BSP payments before deadline",
  "Calculate margin and profit per booking; prepare sales / outstanding / profit reports",
  "Classify input and output GST; calculate, prepare and file GST returns",
  "Deduct, deposit and file TDS returns",
  "Calculate salaries, deduct PF / ESI / PT, deposit payroll-related dues",
  "Prepare records for audit and CA; maintain statutory records",
];

export default function AccountingPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Domain · Accounting & Finance"
            title="Double-entry discipline, driven from chat."
            description="Voyagent doesn't replace your accounting system — it drives it. Journals post through the accounting agent with the debit==credit invariant enforced in code; receivables and payables age into 0-30 / 31-60 / 61-90 / 90+ buckets; the Tally XML protocol layer is built and waiting on the desktop bridge round-trip to a real instance."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="bsp-match" />

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Live today
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Running on main against the deployed environment.
          </p>
          <ul className="mt-6 grid gap-3 text-sm text-slate-700 md:grid-cols-2">
            {LIVE_TODAY.map((a) => (
              <li
                key={a}
                className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50/40 px-4 py-3"
              >
                <span
                  aria-hidden="true"
                  className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-500"
                />
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Shipping next
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Gated on a real Tally instance or additional driver work. Not live today.
          </p>
          <ul className="mt-6 grid gap-3 text-sm text-slate-700 md:grid-cols-2">
            {SHIPPING_NEXT.map((a) => (
              <li
                key={a}
                className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50/40 px-4 py-3"
              >
                <span
                  aria-hidden="true"
                  className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500"
                />
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Representative activity inventory
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Drawn from the verbatim activity inventory of a working agency. This
            is the domain surface the accounting agent is being built to cover;
            not every item is wired end-to-end today.
          </p>
          <ul className="mt-6 grid gap-3 text-sm text-slate-700 md:grid-cols-2">
            {ACTIVITIES.map((a) => (
              <li
                key={a}
                className="flex gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3"
              >
                <span
                  aria-hidden="true"
                  className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent"
                />
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </section>

        <ScreenshotMock variant="reconciliation" />
      </div>

      <CtaBand />
    </>
  );
}
