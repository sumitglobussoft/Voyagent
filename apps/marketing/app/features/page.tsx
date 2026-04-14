import type { Metadata } from "next";
import {
  Plane,
  Calculator,
  FileText,
  Receipt,
  Send,
  Check,
  RefreshCcw,
  Search,
  Users,
  Settings,
  User,
} from "@voyagent/icons";

import { CtaBand } from "@/components/CtaBand";
import { FeatureGrid } from "@/components/FeatureGrid";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Features",
  description:
    "What Voyagent actually ships today: real-time agentic chat, approval-gated tool calls, enquiries, double-entry reports, per-tenant isolation, in-house auth, native deployment.",
  alternates: { canonical: absoluteUrl("/features") },
};

// Every card here reflects a capability that is on main and running at
// voyagent.globusdemos.com as of 2026-04-14. No aspirational items.
const SHIPPED = [
  {
    title: "Real-time agentic chat",
    description:
      "SSE streaming from FastAPI with Anthropic prompt caching. Tool calls render inline; chat reconnects replay from Last-Event-ID so dropped networks don't lose context.",
    icon: Send,
  },
  {
    title: "Approval-gated tool calls",
    description:
      "Irreversible actions pause for a human. Finance resolves pending calls from /app/approvals with cross-tenant guard and TTL expiry on every ticket.",
    icon: Check,
  },
  {
    title: "Three domain agents",
    description:
      "ticketing_visa, hotels_holidays, accounting — each with its own scoped tool set. Hotels can't see accounting tools; agents are isolated at the runtime boundary.",
    icon: Plane,
  },
  {
    title: "Enquiry CRUD + lifecycle",
    description:
      "Track enquiries through new → quoted → booked or cancelled. Promote any enquiry into a chat session in one click; the agent inherits the context.",
    icon: FileText,
  },
  {
    title: "Receivables & payables reports",
    description:
      "0-30 / 31-60 / 61-90 / 90+ aging buckets computed live against the invoices + bills + journal_entries tables. Itinerary report reads straight from chat sessions.",
    icon: Receipt,
  },
  {
    title: "Double-entry ledger",
    description:
      "Every JournalEntry is debits = credits per currency, enforced in the canonical model. Postings from the accounting agent are gated behind the same approval flow.",
    icon: Calculator,
  },
  {
    title: "Per-tenant isolation",
    description:
      "Tenant id is a first-class column on every domain row, every driver invocation, and every audit event. Credentials, data and sessions never cross the tenancy boundary.",
    icon: Users,
  },
  {
    title: "In-house auth",
    description:
      "argon2id password hashing, HS256 JWT access tokens (1h), opaque refresh tokens (30d, single-use rotation), httpOnly cookies on web, SecureStore on desktop and mobile.",
    icon: User,
  },
  {
    title: "Canonical domain model",
    description:
      "Pydantic v2 spec for flights, finance and lifecycle; hotel, visa and transfer skeletons in place. Currency on every money field; no driver types leak upward.",
    icon: Settings,
  },
  {
    title: "Native deployment",
    description:
      "Single Ubuntu host, systemd-supervised Python and Node processes, native Postgres 16 + native Redis 7 + native nginx with certbot TLS. No Docker in the request path.",
    icon: Search,
  },
  {
    title: "SSE streaming",
    description:
      "Server-sent events for chat; reconnection replays from Last-Event-ID. Long tool runs stream progress tokens instead of spinning on a blank screen.",
    icon: RefreshCcw,
  },
  {
    title: "Append-only audit log",
    description:
      "Every side-effect tool call records actor, tenant, inputs, outputs, the driver invoked, approvals and timestamps. Auth failures ride the same stream, rate-limited.",
    icon: FileText,
  },
];

export default function FeaturesPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="What's shipped"
            title="Features that are on main today."
            description="No roadmap mixed in. Every card below is a capability running at voyagent.globusdemos.com right now — see the integrations page for vendor-by-vendor driver status, and the changelog for session-by-session history."
          />
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-20 px-5 py-20 md:px-8 md:py-28">
        <section>
          <FeatureGrid items={SHIPPED} columns={3} />
        </section>
      </div>

      <CtaBand />
    </>
  );
}
