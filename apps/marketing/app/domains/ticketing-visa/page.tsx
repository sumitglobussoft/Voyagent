import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { ScreenshotMock } from "@/components/ScreenshotMock";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Ticketing & Visa",
  description:
    "Chat-driven enquiry to quote with the ticketing_visa agent. Amadeus self-service fare search + PNR creation live today; ticket issuance and VFS automation are gated on credentials and selectors.",
  alternates: { canonical: absoluteUrl("/domains/ticketing-visa") },
};

const LIVE_TODAY = [
  "Chat-driven enquiry to quote via the ticketing_visa agent",
  "Amadeus self-service sandbox for fare search and PNR creation",
  "BSP India HAF file parser with a 164-airline IATA allow-list",
  "VFS portal browser-runner skeleton (routing, session, handoff)",
  "CAPTCHA / MFA handoff from VFS runner to a human (PermanentError route)",
];

const SHIPPING_NEXT = [
  "Amadeus production tier for real ticket issuance (blocked on enterprise credentials)",
  "Per-tenant VFS selectors for automated visa form fill and appointment booking",
  "BSP India settlement posting workflow",
  "Sabre, Travelport / Galileo, TBO and airline NDC feeds as additional drivers",
];

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
            title="Enquiry to quote in one chat. Issuance and portal automation on deck."
            description="The ticketing_visa agent runs fare search and PNR creation against the Amadeus self-service sandbox today. Ticket issuance is blocked on enterprise-tier credentials; VFS automation is blocked on per-tenant selectors. The full activity inventory below is the roadmap — the list above it is what actually runs on main."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-16 px-5 py-16 md:px-8 md:py-24">
        <ScreenshotMock variant="chat" />

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
            Gated on credentials, selectors or additional driver work. Not live today.
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
            is the domain surface the ticketing_visa agent is being built to
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

        <ScreenshotMock variant="approval" />
      </div>

      <CtaBand />
    </>
  );
}
