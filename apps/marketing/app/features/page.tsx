import type { Metadata } from "next";
import {
  Plane,
  Hotel,
  Calculator,
  FileText,
  Receipt,
  CreditCard,
  Send,
  Check,
  AlertTriangle,
  RefreshCcw,
  Search,
  Users,
  Settings,
  User,
  Download,
} from "@voyagent/icons";

import { CtaBand } from "@/components/CtaBand";
import { FeatureGrid } from "@/components/FeatureGrid";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Features",
  description:
    "Voyagent feature catalog: agent UX, domain coverage, vendor-agnosticism, finance-grade invariants, security, and tri-platform delivery.",
  alternates: { canonical: absoluteUrl("/features") },
};

const AGENT_UX = [
  {
    title: "Natural-language enquiry",
    description:
      "Paste a WhatsApp forward or type free-form. The orchestrator classifies intent and opens a typed Enquiry.",
    icon: Send,
  },
  {
    title: "Streamed responses",
    description:
      "SSE streaming with Last-Event-ID reconnect means long tool runs (fare search, reconciliation) stream progress, not spinners.",
    icon: RefreshCcw,
  },
  {
    title: "Approval gating on every side-effect",
    description:
      "Tools carry side_effect + reversible flags. Irreversible actions always pause for human confirmation.",
    icon: Check,
  },
];

const DOMAIN = [
  {
    title: "Ticketing & Visa",
    description:
      "Fare search, PNR ops, ticket issue, queue handling, web check-in, visa checklist and appointment tracking.",
    icon: Plane,
  },
  {
    title: "Hotels & Holidays",
    description:
      "Multi-supplier rate aggregation, package costing, voucher issuance, revisions, post-booking support.",
    icon: Hotel,
  },
  {
    title: "Accounting & Finance",
    description:
      "Invoicing, collections, supplier payments, BSP/card/bank reconciliation, GST/TDS, management reporting.",
    icon: Calculator,
  },
];

const VENDOR = [
  {
    title: "Adapter-first by construction",
    description:
      "One driver per external system. Canonical model never sees Amadeus or Tally types — add a driver, not a redesign.",
    icon: Settings,
  },
  {
    title: "Capability manifests",
    description:
      "Each driver declares what it can and can't do. The orchestrator selects drivers at runtime per tenant.",
    icon: FileText,
  },
  {
    title: "Graceful degradation",
    description:
      "When a driver can't auto-post, Voyagent falls back — e.g. a Tally-importable XML instead of a direct post.",
    icon: AlertTriangle,
  },
  {
    title: "Per-tenant driver isolation",
    description:
      "Tenant A's Amadeus credentials and Tenant B's are fully segregated. No cross-tenant driver reuse.",
    icon: Users,
  },
];

const FINANCE = [
  {
    title: "Double-entry invariants",
    description:
      "Every JournalEntry is debits = credits per currency, enforced in the canonical model, not hoped for.",
    icon: Receipt,
  },
  {
    title: "BSP reconciliation",
    description:
      "BSPlink India parser matches ticket sales, refunds, commission and flags ADM/ACM candidates with evidence.",
    icon: Check,
  },
  {
    title: "Append-only audit log",
    description:
      "Every side-effect tool call is logged with actor, inputs, outputs, driver invoked, and approval trail.",
    icon: FileText,
  },
  {
    title: "Per-currency balancing",
    description:
      "Books balance per currency, not per aggregate — BOM rupees and DXB dirhams stay legible.",
    icon: Calculator,
  },
];

const SECURITY = [
  {
    title: "Per-tenant credential encryption",
    description:
      "Envelope encryption over per-tenant KMS keys. Enterprise BYO-key supported at the vault interface.",
    icon: CreditCard,
  },
  {
    title: "RBAC on approval roles",
    description:
      "agent / senior_agent / accountant / admin / auditor — scoped per domain and action.",
    icon: User,
  },
  {
    title: "Session + action audit",
    description:
      "Auth failures are rate-limited and audit-logged. Every action has a traceable actor.",
    icon: Search,
  },
  {
    title: "Data residency abstraction",
    description:
      "DPDP (India) + GDPR-ready. Residency is a platform primitive, not a patch.",
    icon: Download,
  },
];

const DELIVERY = [
  {
    title: "Web, desktop, mobile",
    description:
      "Next.js web for light users, Tauri desktop for GDS/Tally power users, Expo mobile for reports and approvals.",
    icon: Plane,
  },
  {
    title: "SSE streaming",
    description:
      "Server-sent events for chat; reconnection replays from Last-Event-ID so dropped networks don't lose context.",
    icon: RefreshCcw,
  },
  {
    title: "Resilient by default",
    description:
      "Durable workflows via Temporal for long-running tool calls (visa portals, BSP parsing, reconciliations).",
    icon: Check,
  },
];

export default function FeaturesPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Feature catalog"
            title="Everything Voyagent ships with — and what's explicitly planned."
            description="Organized by the six surfaces that matter: agent experience, domain coverage, vendor-agnosticism, finance-grade invariants, security, and delivery."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-20 px-5 py-20 md:px-8 md:py-28">
        <section>
          <SectionHeader
            eyebrow="Agent experience"
            title="Chat that actually does work."
          />
          <div className="mt-10">
            <FeatureGrid items={AGENT_UX} columns={3} />
          </div>
        </section>

        <section>
          <SectionHeader
            eyebrow="Domain coverage"
            title="Three domains. 100+ activities automated."
            description="Every workflow traces back to the verbatim activity inventory — see the full list in the docs."
          />
          <div className="mt-10">
            <FeatureGrid items={DOMAIN} columns={3} />
          </div>
        </section>

        <section>
          <SectionHeader
            eyebrow="Vendor-agnostic"
            title="An integration platform first, an AI product second."
          />
          <div className="mt-10">
            <FeatureGrid items={VENDOR} columns={4} />
          </div>
        </section>

        <section>
          <SectionHeader
            eyebrow="Finance-grade"
            title="Books accountants will actually sign off on."
          />
          <div className="mt-10">
            <FeatureGrid items={FINANCE} columns={4} />
          </div>
        </section>

        <section>
          <SectionHeader
            eyebrow="Security & compliance"
            title="Multi-tenant by construction."
          />
          <div className="mt-10">
            <FeatureGrid items={SECURITY} columns={4} />
          </div>
        </section>

        <section>
          <SectionHeader
            eyebrow="Delivery"
            title="Tri-platform. Streaming. Resilient."
          />
          <div className="mt-10">
            <FeatureGrid items={DELIVERY} columns={3} />
          </div>
        </section>
      </div>

      <CtaBand />
    </>
  );
}
