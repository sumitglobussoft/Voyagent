import type { Metadata } from "next";
import Link from "next/link";
import {
  AlertTriangle,
  Calculator,
  CreditCard,
  FileText,
  Hotel,
  Plane,
  Receipt,
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

const PAIN_POINTS = [
  {
    icon: AlertTriangle,
    title: "Tool sprawl",
    body: "Your team moves between Amadeus, a visa portal, a hotel bank, Tally and email for a single booking. Each hand-off is a place to lose a margin or a deadline.",
  },
  {
    icon: AlertTriangle,
    title: "Repetitive data entry",
    body: "Passenger details, fare breakdowns, supplier bills and tax lines are retyped three or four times per sale. Accountants spend days closing books that should be minutes.",
  },
  {
    icon: AlertTriangle,
    title: "Brittle reconciliation",
    body: "BSP statements, card settlements and supplier bills get cross-checked by hand. Discrepancies surface weeks late, when the client has already travelled.",
  },
];

const TIERS = [
  {
    tier: "01 — Identify & Collect",
    icon: FileText,
    title: "Structured intake by conversation.",
    body: "An agent gathers the enquiry, passports, travel history and preferences in a single chat. No more eight-tab form filling, no more missed checklist items before a visa submission.",
  },
  {
    tier: "02 — Verify",
    icon: Receipt,
    title: "Deterministic checks, narrated clearly.",
    body: "Voyagent verifies passport validity, visa checklist completeness, fare legality, and BSP reconciliation using rule-based matchers. The LLM explains findings; it never invents the match.",
  },
  {
    tier: "03 — Act",
    icon: CreditCard,
    title: "Side-effects behind explicit approval.",
    body: "Issuing a ticket, submitting a visa, posting a journal entry or sending a payment all require a human to approve the exact action. Every approval is recorded with actor, inputs, outputs and driver.",
  },
];

const STATS = [
  { value: "3", label: "Domain agents live" },
  { value: "SSE", label: "Streaming chat, tool calls in-band" },
  { value: "Approvals", label: "Web inbox for finance" },
  { value: "Double-entry", label: "Ledger enforced in code" },
  { value: "Per-tenant", label: "Credentials and data isolated" },
  { value: "~750 tests", label: "Python + TypeScript suites" },
];

const SHIPPED_TODAY = [
  {
    title: "Real-time agentic chat",
    body: "SSE streaming from FastAPI with Anthropic prompt caching. Tool calls are rendered inline; responses arrive as they're produced.",
  },
  {
    title: "Approval-gated tool calls",
    body: "Finance resolves pending actions from a web inbox at /app/approvals. Cross-tenant guard and TTL expiry enforced at the service layer.",
  },
  {
    title: "Enquiry CRUD + lifecycle",
    body: "Track enquiries through new, quoted, booked and cancelled states. Promote any enquiry into a chat session in one click.",
  },
  {
    title: "Receivables & payables, live",
    body: "0-30 / 31-60 / 61-90 / 90+ aging buckets computed against real invoices, bills and double-entry journal entries.",
  },
  {
    title: "Three domain agents",
    body: "ticketing_visa, hotels_holidays and accounting — each with its own scoped tool set. Hotels can't see accounting tools, and vice versa.",
  },
  {
    title: "In-house auth",
    body: "argon2id passwords, HS256 JWTs (1h access, 30d single-use refresh), httpOnly cookies on web, SecureStore on mobile and desktop.",
  },
];

const SHIPPING_NEXT = [
  {
    title: "Ticket issuance on Amadeus production",
    body: "Sandbox is wired; enterprise credentials are the blocker. Until those land, ticketing agents draft PNRs and stop at issuance.",
  },
  {
    title: "TBO hotel booking",
    body: "Search and price re-check are live. Booking is stubbed behind the approval flow until TBO sandbox credentials are issued.",
  },
  {
    title: "Tally desktop bridge",
    body: "Tally XML-over-:9000 is partial. A Tauri-side bridge for desktop-local posting is scaffolded and lands next.",
  },
  {
    title: "VFS per-tenant selectors",
    body: "The Playwright-based browser runner is in place. Per-tenant selector packs and credential vault wiring follow.",
  },
];

const PRINCIPLES = [
  {
    title: "Replaces ops. Not a copilot.",
    body: "Voyagent is the chat interface and the workflow engine. It drives the GDS, the visa portal and the accounting system end-to-end so your team stops switching tools, not so they copy-paste faster.",
  },
  {
    title: "Vendor-agnostic by architecture.",
    body: "A canonical domain model sits above a driver layer. Each GDS, accounting system and portal is a driver behind a stable interface — swap Amadeus for Sabre without touching an agent, add Zoho Books without touching a prompt.",
  },
  {
    title: "Accountants-grade, not demo-grade.",
    body: "Double-entry invariants enforced at the model layer. BSP reconciliation deterministic, not LLM-guessed. GST and TDS handled behind country-scoped drivers so the books pass an audit, not just a screenshot.",
  },
  {
    title: "India-first, globalization-safe.",
    body: "We ship to Indian agencies now — Tally, BSP India, UPI, DPDP. The canonical model carries currency on every money field, tax as regime-tagged lines, and national IDs as country-scoped entries so the same product works in Dubai and London next year.",
  },
];

export default function LandingPage() {
  return (
    <>
      <Hero />

      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-shell px-5 py-10 text-center md:px-8">
          <div className="mb-6 text-xs font-semibold uppercase tracking-widest text-slate-500">
            Built to integrate with
          </div>
        </div>
        <LogoMarquee />
        <div className="mx-auto w-full max-w-shell px-5 pb-10 text-center md:px-8">
          <p className="mt-2 text-xs text-slate-500">
            Voyagent is not affiliated with or endorsed by any of the systems
            listed. Trademarks belong to their respective owners.
          </p>
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
          <SectionHeader
            eyebrow="The problem"
            title="The modern travel agency runs on duct tape."
            description="Every booking touches a GDS, a visa portal, a hotel bank, a payment gateway, and an accounting system. Staff stitch it together by hand — and the margin bleeds into the hand-offs."
          />
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {PAIN_POINTS.map((p) => {
              const Icon = p.icon;
              return (
                <div
                  key={p.title}
                  className="rounded-xl border border-slate-200 bg-white p-6 shadow-soft-md"
                >
                  <div
                    className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50 text-amber-600"
                    aria-hidden="true"
                  >
                    <Icon width={20} height={20} />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">
                    {p.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    {p.body}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="What you get today"
          title="Shipped, deployed, and running at voyagent.globusdemos.com."
          description="These are the capabilities an early-access agency can use this week. Nothing on this list is a promise — it's on main and it's live."
        />
        <div className="mx-auto mt-10 grid max-w-5xl gap-6 md:grid-cols-2 lg:grid-cols-3">
          {SHIPPED_TODAY.map((item) => (
            <div
              key={item.title}
              className="rounded-xl border border-slate-200 bg-white p-6 shadow-soft-md"
            >
              <h3 className="text-base font-semibold text-slate-900">
                {item.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                {item.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
          <SectionHeader
            eyebrow="Shipping next"
            title="What's wired but not yet unblocked."
            description="The code paths exist; the blockers are external — vendor credentials, sandbox access, or a desktop-host bridge that's one session away. No invented timelines."
          />
          <div className="mx-auto mt-10 grid max-w-5xl gap-6 md:grid-cols-2">
            {SHIPPING_NEXT.map((item) => (
              <div
                key={item.title}
                className="rounded-xl border border-slate-200 bg-white p-6 shadow-soft-md"
              >
                <h3 className="text-base font-semibold text-slate-900">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="The product"
          title="One chat interface. Three domains. Every vendor."
          description="Voyagent covers the full ops surface of a travel agency. Not a ticketing tool with accounting bolted on, not a CRM pretending to be a workflow engine — the whole stack, driven from one conversation."
        />
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          <DomainCard
            title="Ticketing & Visa"
            summary="Enquiry to issuance to web check-in, across every GDS, consolidator and visa portal."
            href="/domains/ticketing-visa"
            icon={Plane}
            bullets={[
              "Fare search across Amadeus, Sabre, Travelport and consolidators",
              "PNR lifecycle, queue handling, ticket issuance",
              "Visa checklist, form fill, appointment, status tracking",
              "Schedule changes, cancellations, refunds",
            ]}
          />
          <DomainCard
            title="Hotels & Holidays"
            summary="Package building from multiple suppliers — hotels, transport, tours and Umrah — with costing and vouchers."
            href="/domains/hotels-holidays"
            icon={Hotel}
            bullets={[
              "Multi-supplier rate aggregation and comparison",
              "Package costing, quotation and revision workflows",
              "Voucher issuance and post-booking support",
              "Supplier billing reconciliation",
            ]}
          />
          <DomainCard
            title="Accounting & Finance"
            summary="Invoices, collections, supplier payments, BSP reconciliation, GST and TDS — posted into the accounting system you already run."
            href="/domains/accounting"
            icon={Calculator}
            bullets={[
              "Invoicing and receipts posted into Tally, Zoho Books or Busy",
              "BSP, card, bank and supplier reconciliation",
              "GST, TDS and statutory filings behind country-scoped drivers",
              "Per-booking profit, audit-ready books",
            ]}
          />
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
          <SectionHeader
            eyebrow="How it works"
            title="Three tiers. Every workflow lives on this spine."
            description="Agents identify and collect the requirement, verify it against deterministic rules, and only then act. Side-effects are gated behind human approval — the LLM never posts a journal entry on its own."
          />
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {TIERS.map((t) => {
              const Icon = t.icon;
              return (
                <div
                  key={t.tier}
                  className="rounded-xl border border-slate-200 bg-white p-7 shadow-soft-md"
                >
                  <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary">
                    <Icon width={20} height={20} aria-hidden="true" />
                  </div>
                  <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                    {t.tier}
                  </div>
                  <div className="mt-2 text-lg font-semibold text-slate-900">
                    {t.title}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    {t.body}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="Design principles"
          title="What Voyagent is, honestly."
          description="Four decisions that make this product different from the copilots and add-ons already in the market."
          align="center"
        />
        <div className="mx-auto mt-10 grid max-w-4xl gap-6 md:grid-cols-2">
          {PRINCIPLES.map((p) => (
            <div
              key={p.title}
              className="rounded-xl border border-slate-200 bg-white p-7 shadow-soft-md"
            >
              <h3 className="text-lg font-semibold text-slate-900">
                {p.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                {p.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto grid w-full max-w-shell gap-12 px-5 py-20 md:grid-cols-2 md:gap-10 md:px-8 md:py-28">
          <div>
            <SectionHeader
              eyebrow="Under the hood"
              title="Adapter-first architecture."
              description="The AI is not the hard part. The adapter layer is. Voyagent is a canonical domain model with drivers per vendor, agents on top, and platform services — credential vault, audit, RBAC — underneath."
            />
            <div className="mt-8 flex flex-wrap gap-3">
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
                Open the doc
              </Link>
            </div>
          </div>
          <ArchitectureDiagram compact />
        </div>
      </section>

      <section className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
        <SectionHeader
          eyebrow="A real flow"
          title="One chat, from enquiry to reconciliation."
          description="An operator asks for a quote. Voyagent searches fares across the configured GDS, prices the hotel, builds the quotation, books the PNR on human approval, invoices the client in Tally, and reconciles the ticket when the next BSP statement lands. The operator never leaves the chat."
        />
        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <ScreenshotMock variant="chat" />
          <ScreenshotMock variant="quote" />
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-28">
          <SectionHeader
            eyebrow="Scope, honestly"
            title="What we will stand behind."
            description="No fabricated MRR, no invented 'hours saved' numbers, no customer logos we don't have. Just the properties of the system that are true of main today."
            align="center"
          />
          <div className="mt-10 grid gap-4 md:grid-cols-3 lg:grid-cols-6">
            {STATS.map((s) => (
              <StatBadge key={s.label} value={s.value} label={s.label} />
            ))}
          </div>
        </div>
      </section>

      <TestimonialPlaceholder />
      <CtaBand />
    </>
  );
}
