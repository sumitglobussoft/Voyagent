import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Accounting & Finance",
  description:
    "Invoicing, collections, supplier payments, BSP / card / bank reconciliation, GST and TDS — posted into the accounting stack you already use.",
  alternates: { canonical: absoluteUrl("/domains/accounting") },
};

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
            title="Books accountants will actually sign off on."
            description="Voyagent doesn't replace your accounting system — it drives it. Invoices, receipts, supplier payments, BSP reconciliation, GST, TDS, and management reports, all posted into Tally today and Zoho / Busy / QuickBooks / SAP on the roadmap."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="bsp-match" />

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Representative activities
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Drawn from the verbatim activity inventory. Full accounting and
            statutory coverage is the goal; the items below are
            representative, not exhaustive.
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
