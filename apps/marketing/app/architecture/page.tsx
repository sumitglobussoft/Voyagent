import type { Metadata } from "next";
import Link from "next/link";

import { ArchitectureDiagram } from "@/components/ArchitectureDiagram";
import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Architecture",
  description:
    "The six-layer adapter-first architecture behind Voyagent — platform services, canonical model, drivers, tool runtime, agents, and clients.",
  alternates: { canonical: absoluteUrl("/architecture") },
};

const LAYERS = [
  {
    name: "Layer 0 — Platform Services",
    summary:
      "Multi-tenancy, RBAC, audit log, approval workflow engine, credential vault, observability, billing.",
    body: "Every other layer assumes this exists. Roles (agent / senior_agent / accountant / admin / auditor) are scoped per domain and per action. Every side-effect tool call is recorded immutably for CA/auditor review.",
  },
  {
    name: "Layer 1 — Canonical Domain Model",
    summary:
      "One internal vocabulary. Enquiry, Passenger, Itinerary, Fare, PNR, Booking, VisaFile, Voucher, Invoice, JournalEntry, BSPReport, Reconciliation.",
    body: "Vendor fields never leak upward. Adding a new GDS means writing a driver that maps its API to the canonical Fare / PNR / Booking — no agent change required. The model is versioned strictly.",
  },
  {
    name: "Layer 2 — Driver / Adapter Layer",
    summary:
      "FareSearch, PNR, Hotel, Transport, VisaPortal, Accounting, Payment, BSP, Card, Bank, Messaging, Document, Statutory.",
    body: "One driver per external system. Each publishes a capability manifest declaring exactly what it supports. The orchestrator selects drivers at runtime based on tenant configuration and capability availability — so if a tenant's accounting system can't auto-post, Voyagent gracefully falls back to a Tally-importable XML.",
  },
  {
    name: "Layer 3 — Tool Runtime",
    summary:
      "Canonical tools with side_effect, reversible, and approval_required flags.",
    body: "Irreversible side-effects — issue_ticket, post_journal_entry, submit_visa, disburse_payment — always require explicit human confirmation. Reversible actions (hold PNR, draft quote) run freely.",
  },
  {
    name: "Layer 4 — Agents",
    summary:
      "Orchestrator, three domain agents (ticketing_visa, hotels_holidays, accounting), cross-cutting agents (document_verifier, reconciler, reporter).",
    body: "The Anthropic Python SDK with prompt caching enabled from day one, wrapped in our own orchestrator and per-domain state machines: enquiry → quote → book → deliver → post-sale.",
  },
  {
    name: "Layer 5 — Clients",
    summary:
      "Web (Next.js), Desktop (Tauri 2), Mobile (Expo / React Native).",
    body: "Desktop is the power-user client — it hosts integrations that need local OS access (GDS terminals, Tally ODBC/XML, smart-card readers, local printers). Web is the thin SPA. Mobile handles reports, approvals, and a remote-control relay paired to a desktop session over WebSocket.",
  },
];

export default function ArchitecturePage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Architecture"
            title="Six layers. Adapter-first. No AI magic."
            description="The AI is not the hard part — the adapter layer is. Get vendor-agnosticism right and onboarding a new GDS or accounting system becomes a driver, not a redesign."
          />
        </div>
      </section>

      <div className="mx-auto w-full max-w-shell px-5 pt-16 md:px-8">
        <ArchitectureDiagram />
      </div>

      <div className="mx-auto flex w-full max-w-shell flex-col gap-10 px-5 py-16 md:px-8 md:py-24">
        {LAYERS.map((layer) => (
          <article
            key={layer.name}
            className="rounded-2xl border border-slate-200 bg-white p-7 shadow-soft-md"
          >
            <h2 className="text-xl font-bold tracking-tight text-slate-900 md:text-2xl">
              {layer.name}
            </h2>
            <p className="mt-3 text-base font-medium text-primary">
              {layer.summary}
            </p>
            <p className="mt-3 text-base leading-relaxed text-slate-700">
              {layer.body}
            </p>
          </article>
        ))}

        <div className="rounded-2xl border border-primary-100 bg-primary-50/60 p-7">
          <h3 className="text-lg font-semibold text-slate-900">
            Read the full architecture doc
          </h3>
          <p className="mt-2 text-sm text-slate-700">
            The detailed version — driver contracts, canonical-model design
            rationale, invariants — lives in the repo alongside the code.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/docs/ARCHITECTURE"
              className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white"
            >
              Architecture doc
            </Link>
            <Link
              href="/docs/CANONICAL_MODEL"
              className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800"
            >
              Canonical model
            </Link>
            <Link
              href="/docs/DECISIONS"
              className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800"
            >
              Decision log
            </Link>
          </div>
        </div>
      </div>

      <CtaBand />
    </>
  );
}
