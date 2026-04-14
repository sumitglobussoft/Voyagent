import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Ticketing & Visa",
  description:
    "Enquiry to issuance to web check-in. Multi-GDS fare search, PNR operations, visa portal automation, and schedule-change handling.",
  alternates: { canonical: absoluteUrl("/domains/ticketing-visa") },
};

const ACTIVITIES = [
  "Identify destination, dates, passenger types, departure city, airline and flight preferences",
  "Check passport validity, visa category and official visa rules via embassy / consulate / VFS portals",
  "Prepare visa checklists adjusted for employment type, finances and travel history",
  "Collect, verify and cross-check client documents before submission",
  "Search fares across GDS, airline websites, consolidators and other fare sources",
  "Build itineraries, prepare quotations with inclusions, exclusions and payment terms",
  "Hold or lock bookings, confirm PNRs, issue tickets",
  "Fill visa forms, upload documents, pay visa fees, book appointments",
  "Guide clients for biometrics, interview and submission; track visa status",
  "Handle approval updates, rejection review and reapplication preparation",
  "Do web check-in and share boarding passes",
  "Monitor schedule changes and keep clients informed",
  "Share final itinerary, visa copy and travel readiness instructions",
  "Handle cancellations and refunds where required",
];

export default function TicketingVisaPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Domain · Ticketing & Visa"
            title="From enquiry to issuance, across every GDS and portal."
            description="Voyagent drives the full ticketing + visa workflow in one chat — fare search, PNR operations, visa portal automation (including the browser-automated ones without APIs), and post-booking follow-through."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="chat" />

        <section>
          <h2 className="text-2xl font-bold tracking-tighter text-slate-900">
            Representative activities
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Drawn from the verbatim activity inventory. Full coverage of the
            customer&rsquo;s ticketing &amp; visa workload is the goal; the
            items below are representative, not exhaustive.
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

        <ScreenshotMock variant="approval" />
      </div>

      <CtaBand />
    </>
  );
}
