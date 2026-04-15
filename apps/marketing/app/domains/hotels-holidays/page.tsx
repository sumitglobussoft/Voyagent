import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Hotels & Holidays",
  description:
    "Chat-driven hotel search and price re-check via the TBO driver, with an approval-gated booking flow. Booking itself is blocked on TBO sandbox credentials today.",
  alternates: { canonical: absoluteUrl("/domains/hotels-holidays") },
};

const LIVE_TODAY = [
  "Chat-driven hotel search and price re-check via the TBO driver (real HTTP wiring)",
  "hotels_holidays agent with an approval gate in front of booking (the gate works; the booking call is stubbed)",
  "Canonical hotel models: HotelRoom, HotelRate, HotelProperty, HotelSearchResult, BoardBasis enum",
];

const SHIPPING_NEXT = [
  "TBO booking / cancel / read, once sandbox credentials land (today we return CapabilityNotSupportedError)",
  "Hotelbeds as a second hotel vendor — decision pending",
];

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
            title="Hotel search live. Booking approval gate live. Booking call waiting on creds."
            description="One chat drives hotel search and price re-check against TBO today, backed by the canonical HotelRoom / HotelRate / HotelProperty models. The approval gate in front of booking is wired end-to-end; the booking call itself is stubbed until TBO sandbox credentials land."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="quote" />

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
            Gated on credentials or vendor decisions. Not live today.
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
            is the domain surface the hotels_holidays agent is being built to
            cover; not every item is wired end-to-end today.
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
