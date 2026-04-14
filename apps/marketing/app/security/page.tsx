import type { Metadata } from "next";

import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Security",
  description:
    "Authentication, per-tenant isolation, envelope encryption, RBAC on approvals, append-only audit log, DPDP/GDPR-ready data residency.",
  alternates: { canonical: absoluteUrl("/security") },
};

const SECTIONS = [
  {
    title: "Authentication",
    body: "Clerk-issued JWTs verified with RS256 via JWKS. A short-lived access token on every request; refresh happens at the edge, never the driver layer. Token revocation flags are wired through so an admin can sever a session without waiting for natural expiry.",
  },
  {
    title: "Multi-tenancy",
    body: "One tenant per agency, with sub-tenants for branches and desks. Tenancy is a first-class column on every domain object — queries, audit rows, and driver invocations all carry tenant_id and are isolated at the data plane.",
  },
  {
    title: "Credential vault",
    body: "Per-tenant credentials (GDS, accounting, payment gateways, portal sessions) are stored under envelope encryption with per-tenant KMS keys. BYO-key is supported at the vault interface for enterprise tenants that require it.",
  },
  {
    title: "RBAC on approvals",
    body: "Roles include agent, senior_agent, accountant, admin, and auditor. Approval workflows are configurable: 'issue_ticket above ₹X requires senior_agent', 'post_journal_entry always requires accountant confirmation'. Scope is per-domain and per-action, not global.",
  },
  {
    title: "Audit log",
    body: "Every side-effect tool call records actor, tenant, inputs, outputs, the driver invoked, approvals, and timestamps — append-only, exportable for CA/auditor review. Auth failures are rate-limited and written to the same stream so brute-force attempts are investigable.",
  },
  {
    title: "Data residency",
    body: "Residency is abstracted for both Indian DPDP Act compliance and GDPR-ready expansion. Tenant data, credentials, and audit rows have declared residency zones; the platform refuses cross-zone reads unless the tenant explicitly opts in.",
  },
];

export default function SecurityPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Security & compliance"
            title="Built for a tenant that moves money, not a demo."
            description="Storing GDS, accounting, card and payment credentials per tenant puts Voyagent in DPDP and PCI-DSS territory from day one. We designed for that reality from the first commit."
          />
        </div>
      </section>

      <div className="mx-auto grid w-full max-w-shell gap-6 px-5 py-16 md:grid-cols-2 md:px-8 md:py-24">
        {SECTIONS.map((section) => (
          <article
            key={section.title}
            className="rounded-2xl border border-slate-200 bg-white p-7 shadow-soft-md"
          >
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              {section.title}
            </h2>
            <p className="mt-3 text-base leading-relaxed text-slate-700">
              {section.body}
            </p>
          </article>
        ))}
      </div>

      <CtaBand />
    </>
  );
}
