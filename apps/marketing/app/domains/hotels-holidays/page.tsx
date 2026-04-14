import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Hotels & Holidays",
  description:
    "Multi-supplier hotel and package building — FIT hotels, land arrangements, tours, Umrah, and custom holidays for any destination.",
  alternates: { canonical: absoluteUrl("/domains/hotels-holidays") },
};

const ACTIVITIES = [
  "Collect holiday / package enquiry with dates, passengers, hotel preference and budget",
  "Understand package category — economy, standard, premium or luxury",
  "Contact hotels and suppliers for contracted rates and availability",
  "Check transport providers for transfers and local movements",
  "Obtain land, hotel and transport rates",
  "Consolidate hotel, transport, visa, flight and service charges",
  "Prepare package costing and quotation with full inclusions / exclusions",
  "Include travel dates, hotel names, number of nights, transport, visa and total cost",
  "Share quotation, explain package, clarify inclusions and exclusions",
  "Revise packages based on budget, date, hotel, airline or room changes",
  "Reconfirm hotel and transport availability after client approval",
  "Confirm supplier booking; issue hotel, transport and land vouchers",
  "Share final itinerary and brief clients on travel readiness",
  "Handle cancellations, missing billings and refunds",
  "Cross-check supplier billing against bookings",
];

export default function HotelsHolidaysPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Domain · Hotels & Holidays"
            title="Build packages from many suppliers as if they were one."
            description="FIT hotels, land arrangements, tours, Umrah, and custom holidays for any destination. One chat consolidates rates across suppliers and produces a costed, client-ready package."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="quote" />

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Representative activities
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Drawn from the verbatim activity inventory. Full coverage of
            hotels and holidays is the goal; the items below are
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

        <ScreenshotMock variant="chat" />
      </div>

      <CtaBand />
    </>
  );
}
