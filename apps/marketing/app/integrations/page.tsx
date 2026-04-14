import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import {
  IntegrationBadge,
  type IntegrationStatus,
} from "@/components/IntegrationBadge";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Integrations",
  description:
    "Every GDS, accounting system, visa portal, and payment rail Voyagent talks to today — with honest status labels.",
  alternates: { canonical: absoluteUrl("/integrations") },
};

type IntegrationItem = { label: string; status: IntegrationStatus };

const GROUPS: Array<{
  heading: string;
  description: string;
  items: IntegrationItem[];
}> = [
  {
    heading: "GDS & fare sources",
    description:
      "Fare search, PNR create/modify/void, queue handling, ticket issuance.",
    items: [
      { label: "Amadeus", status: "full" },
      { label: "Sabre", status: "planned" },
      { label: "Travelport / Galileo", status: "planned" },
      { label: "TBO", status: "planned" },
      { label: "Riya", status: "planned" },
      { label: "Airline NDC feeds", status: "planned" },
    ],
  },
  {
    heading: "Hotels & land",
    description: "Availability, pricing, booking, voucher issuance.",
    items: [
      { label: "Hotelbeds", status: "planned" },
      { label: "TBO Hotels", status: "planned" },
      { label: "Direct hotel contracts", status: "planned" },
    ],
  },
  {
    heading: "Accounting systems",
    description:
      "Chart-of-accounts read, journal posting, invoice creation, statement read.",
    items: [
      { label: "Tally", status: "full" },
      { label: "Zoho Books", status: "planned" },
      { label: "Busy", status: "planned" },
      { label: "QuickBooks", status: "planned" },
      { label: "SAP / SAP B1", status: "planned" },
      { label: "Marg", status: "planned" },
    ],
  },
  {
    heading: "Visa portals",
    description:
      "Many have no API — these are browser-automated via the Playwright runner.",
    items: [
      { label: "VFS Global", status: "partial" },
      { label: "BLS International", status: "planned" },
      { label: "Embassy / consulate portals", status: "planned" },
    ],
  },
  {
    heading: "Statements & settlement",
    description: "BSP, card and bank statement parsing + reconciliation.",
    items: [
      { label: "BSPlink India", status: "full" },
      { label: "BSP UAE", status: "planned" },
      { label: "BSP UK", status: "planned" },
      { label: "Corporate card statements", status: "planned" },
      { label: "Bank statements (NEFT/RTGS/UPI)", status: "planned" },
    ],
  },
  {
    heading: "Payment rails",
    description: "Inbound collections and outbound disbursements.",
    items: [
      { label: "UPI", status: "planned" },
      { label: "NEFT / RTGS", status: "planned" },
      { label: "Razorpay", status: "planned" },
      { label: "Stripe", status: "planned" },
      { label: "Payment links", status: "planned" },
    ],
  },
];

export default function IntegrationsPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Integrations"
            title="Every vendor in the stack — with honest status."
            description="Voyagent is vendor-agnostic by architecture, which means integrations ship as drivers, not as redesigns. This is where we are today — and what's on the concrete roadmap."
          />
          <div className="mt-6 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 font-medium uppercase tracking-wider text-emerald-700">
              Live
            </span>
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 font-medium uppercase tracking-wider text-amber-700">
              Partial
            </span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 font-medium uppercase tracking-wider text-slate-600">
              Planned
            </span>
          </div>
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-14 px-5 py-16 md:px-8 md:py-24">
        {GROUPS.map((group) => (
          <section key={group.heading}>
            <div>
              <h2 className="text-xl font-bold tracking-tight text-slate-900 md:text-2xl">
                {group.heading}
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                {group.description}
              </p>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {group.items.map((item) => (
                <IntegrationBadge
                  key={item.label}
                  label={item.label}
                  status={item.status}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      <CtaBand />
    </>
  );
}
