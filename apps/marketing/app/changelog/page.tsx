import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand } from "@/components/CtaBand";
import { SectionHeader } from "@/components/SectionHeader";
import { absoluteUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "Changelog",
  description: "What we've shipped, in reverse chronological order.",
  alternates: { canonical: absoluteUrl("/changelog") },
};

interface ChangelogEntry {
  date: string;
  title: string;
  summary: string;
  bullets: React.ReactNode[];
}

const ENTRIES: ChangelogEntry[] = [
  {
    date: "2026-04-15",
    title: "Wave 2: dark mode, i18n, runtime + release infra, ~200 new tests",
    summary:
      "Six parallel agent packs: dark mode + command palette + i18n, product feature polish, per-tenant runtime settings, desktop + mobile release CI, axe-core sweeps, and off-site backup + staging tooling.",
    bullets: [
      <>
        Dark mode across the app (Tailwind <code>darkMode: &quot;class&quot;</code>,
        cookie + localStorage + <code>prefers-color-scheme</code>), toast
        notifications, proper 404 and 500 pages, dynamic favicons.
      </>,
      <>
        Hand-rolled <code>en</code>/<code>hi</code> internationalisation with a
        language switcher on the settings page, plus a Cmd+K command palette
        with fuzzy matching over the in-app actions.
      </>,
      <>
        Chat session delete and rename, audit log CSV export (admin-only
        streaming, 100k row cap), six new enquiry filter parameters, and a
        schema migration that actually populates <code>payload</code> and{" "}
        <code>resolved_by_user_id</code> on approvals.
      </>,
      <>
        Per-tenant agent runtime settings: model override, system prompt
        suffix, rate limits per minute / hour, daily token budget, default
        currency. Cost tracker writes every turn to{" "}
        <code>session_costs</code> and enforces the daily budget.
      </>,
      <>
        <code>GET</code> / <code>PATCH /api/tenant-settings</code> admin-only,
        plus a trial-balance report and tool result cache (read-only
        allowlist, tenant-scoped, 5-minute default TTL).
      </>,
      <>
        <code>.github/workflows/desktop-release.yml</code> (Tauri build matrix
        for macOS, Linux, Windows with PR dry-run) and{" "}
        <code>mobile-release.yml</code> (EAS build + OTA update).
      </>,
      <>
        Passport OCR scaffold in the mobile app with a real ICAO 9303 MRZ
        parser (and a stubbed capture path until a provider is picked). First
        vitest suite wired into <code>apps/mobile</code>.
      </>,
      <>
        Accessibility sweep with <code>@axe-core/playwright</code> across 19
        pages (surfaced 8 pre-existing colour-contrast violations as a UX
        backlog), an opt-in real-Postgres integration fixture, Locust load
        scenarios, and a getting-started walkthrough plus per-driver setup
        pages.
      </>,
      <>
        Off-site Postgres backups via an rclone wrapper (AWS S3, Backblaze
        B2, Cloudflare R2, Wasabi, MinIO, DigitalOcean Spaces), a staging
        environment bootstrap script with systemd unit templates, and a
        secret rotation CLI for the JWT / DB / Redis / metrics / KMS
        secrets.
      </>,
    ],
  },
  {
    date: "2026-04-15",
    title: "Wave 1: team onboarding, auth hardening, observability, agent-to-ledger, ~100 new tests",
    summary:
      "Five parallel packs that unblock real team usage and close the loop between the agent runtime and the ledger.",
    bullets: [
      <>
        Tenant invites with roles, accept-invite flow, and an{" "}
        <code>/app/settings</code> page for admins to manage members.
      </>,
      <>
        <code>PATCH /api/auth/profile</code>, a password reset flow (Redis
        token, log-to-stdout email stub), and three new public pages:{" "}
        <code>/app/forgot-password</code>, <code>/app/reset-password</code>,
        and <code>/app/accept-invite</code>.
      </>,
      <>
        Password strength validator with a 58-entry blocklist, TOTP 2FA with{" "}
        <code>pyotp</code> and a <code>/auth/sign-in-totp</code> second-factor
        endpoint, plus an API key table with scoped <code>vy_</code>-prefixed
        keys.
      </>,
      <>
        GitHub Actions CI (pytest + vitest + Playwright + marketing build),
        automated Postgres backups via a systemd timer with a 30-day
        retention, and a runbook documenting 17 deploy gotchas from
        previous sessions.
      </>,
      <>
        Sentry integration across the API, web app, and marketing site with
        PII-scrubbing <code>before_send</code> hooks and a tenant-tagging
        middleware, plus a Prometheus <code>/internal/metrics</code> endpoint
        gated to localhost or a shared token.
      </>,
      <>
        Mobile sidebar drawer (hidden below 768px with a hamburger
        overlay), enquiries filter bar now responsive, four{" "}
        <code>loading.tsx</code> skeletons for the main list pages.
      </>,
      <>
        Audit log viewer with admin-only RBAC, an approvals-to-audit hook so
        granted and rejected decisions land in the trail, and a passenger
        resolver that mints UUIDv7 identifiers correctly.
      </>,
      <>
        <code>draft_invoice</code> tool for the accounting agent
        (approval-gated, auto-numbering per tenant, <code>Decimal</code>-only
        math), the <code>/reports/trial-balance</code> endpoint, and a demo
        tenant seeder that populates five enquiries, three invoices, three
        bills, five ledger accounts, three balanced journal entries, and
        five audit events &mdash; idempotent via a marker row.
      </>,
    ],
  },
  {
    date: "2026-04-15",
    title: "Demo account and chat path fixes",
    summary:
      "A public demo login and three fixes to the chat path that were biting browser-side SDK consumers.",
    bullets: [
      <>
        Demo account{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          demo@voyagent.globusdemos.com
        </code>{" "}
        exposed on the sign-in page with a &ldquo;Use demo credentials&rdquo;
        pre-fill link.
      </>,
      <>
        Fixed SDK consumers (web, mobile, desktop) to pass an{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /api
        </code>
        -prefixed base URL so the browser-side SDK reaches FastAPI through
        nginx.
      </>,
      <>
        Fixed{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          createSession
        </code>{" "}
        to post an empty body (the API derives tenant and actor from the
        bearer JWT).
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "Approvals inbox and enquiry lifecycle",
    summary:
      "A finance-side approvals inbox and a first-class enquiry object with a full lifecycle.",
    bullets: [
      <>
        New{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /api/approvals
        </code>{" "}
        and{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /app/approvals
        </code>{" "}
        &mdash; list pending tool-call approvals, approve or reject from a
        finance inbox, 15-minute TTL, cross-tenant 404.
      </>,
      <>
        New{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          enquiries
        </code>{" "}
        table and full CRUD:{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /api/enquiries
        </code>{" "}
        and UI at{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /app/enquiries
        </code>{" "}
        (list, filter, search, create, detail, edit, promote-to-chat).
      </>,
      <>
        Status lifecycle{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          new &rarr; quoted &rarr; booked
        </code>{" "}
        with{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          cancelled
        </code>{" "}
        as a terminal state.
      </>,
      <>
        Migration{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          0006_enquiries
        </code>
        .
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "Real-data reports",
    summary:
      "Receivables and payables reports now query real ledger tables instead of fixture data.",
    bullets: [
      <>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          invoices
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          bills
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          ledger_accounts
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          journal_entries
        </code>{" "}
        tables added (migration{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          0005_invoices_ledger
        </code>
        ).
      </>,
      <>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          build_journal_entry
        </code>{" "}
        helper enforces debit == credit in code, not via DB triggers.
      </>,
      <>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /reports/receivables
        </code>{" "}
        and{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /reports/payables
        </code>{" "}
        now query real data with 0-30 / 31-60 / 61-90 / 90+ aging buckets.
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "Eight bug fixes from the error-path test pass",
    summary:
      "A focused sweep of error-path regressions found during an explicit failure-mode test run.",
    bullets: [
      <>Tool output schema validation with retry-once on schema mismatch.</>,
      <>
        Anthropic{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          RateLimitError
        </code>{" "}
        /{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          APIConnectionError
        </code>{" "}
        retry with exponential backoff (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          Retry-After
        </code>{" "}
        honored).
      </>,
      <>
        Sign-in gates on{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          email_verified
        </code>{" "}
        with distinguishable 401 codes (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          email_not_verified
        </code>{" "}
        vs{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          invalid_credentials
        </code>
        ).
      </>,
      <>
        Amadeus JSON decode errors mapped to typed driver errors (no raw
        exceptions through the boundary).
      </>,
      <>
        BSP India HAF parser airline allow-list (164 IATA carriers) plus a
        regex pre-check.
      </>,
      <>
        VFS MFA / 2FA / OTP signals routed to{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          PermanentError
        </code>{" "}
        (was being miscategorized as auth failure).
      </>,
      <>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          pending_approvals.expires_at
        </code>{" "}
        and{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          status=&quot;expired&quot;
        </code>{" "}
        enum value with lazy sweep.
      </>,
      <>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          resolve_approval(actor_tenant_id)
        </code>{" "}
        cross-tenant guard.
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "Hotels domain",
    summary:
      "A hotels_holidays agent, a canonical hotel data model, and a real-HTTP TBO driver for search and re-pricing.",
    bullets: [
      <>
        New{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          hotels_holidays
        </code>{" "}
        agent with approval-gated booking.
      </>,
      <>
        New canonical hotel models:{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          HotelRoom
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          HotelRate
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          HotelProperty
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          HotelSearchResult
        </code>
        , and a{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          BoardBasis
        </code>{" "}
        enum.
      </>,
      <>
        New TBO driver &mdash; search and price re-check wired with real
        HTTP; booking is stubbed pending sandbox credentials.
      </>,
      <>
        Migration{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          0003_passengers
        </code>{" "}
        plus{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          StoragePassengerResolver
        </code>{" "}
        end-to-end.
      </>,
      <>
        Postgres session stores wired by default when{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          VOYAGENT_DB_URL
        </code>{" "}
        is set.
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "In-house auth replaces Clerk everywhere",
    summary:
      "Auth is now owned end-to-end in the platform &mdash; password hashing, JWTs, refresh-token rotation, and a Redis-backed denylist.",
    bullets: [
      <>Argon2id password hashing.</>,
      <>
        HS256 JWT access tokens (1h) plus opaque refresh tokens (30d,
        single-use rotation).
      </>,
      <>
        httpOnly cookies on web (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          voyagent_at
        </code>
        ), SecureStore on mobile and desktop.
      </>,
      <>
        Redis-backed JWT{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          jti
        </code>{" "}
        denylist for revocation.
      </>,
      <>
        Email verification flow stubbed (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /send-verification-email
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          /verify-email
        </code>
        ); real delivery is pending a provider decision.
      </>,
      <>
        Migrations{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          0002_inhouse_auth
        </code>
        .
      </>,
    ],
  },
  {
    date: "2026-04-14",
    title: "Native deployment",
    summary:
      "Docker Compose retired in favor of systemd-supervised native processes on a single host.",
    bullets: [
      <>Migrated off Docker Compose to systemd-supervised processes.</>,
      <>
        Three units:{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          voyagent-api
        </code>{" "}
        (uvicorn :8010),{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          voyagent-web
        </code>{" "}
        (next start :3011), and{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          voyagent-marketing
        </code>{" "}
        (next start :3012).
      </>,
      <>Native Postgres 16 (shared host instance) and native Redis 7.</>,
      <>Single-host nginx plus certbot for TLS.</>,
      <>Removed Clerk, Temporal, and Docker from docs and configs.</>,
    ],
  },
  {
    date: "Earlier",
    title: "Foundations",
    summary:
      "The baseline platform the entries above build on &mdash; canonical model, driver contracts, agent loop, and multi-tenant isolation.",
    bullets: [
      <>In-process agent loop with prompt caching (Anthropic SDK).</>,
      <>
        Three domain agents:{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          ticketing_visa
        </code>
        ,{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          accounting
        </code>
        , and{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-slate-800">
          hotels_holidays
        </code>
        .
      </>,
      <>
        Canonical Pydantic v2 data model: flights, hotels, visa, finance,
        lifecycle.
      </>,
      <>
        Five driver skeletons: Amadeus, TBO, Tally, BSP India, and VFS
        &mdash; all conforming to typed driver contracts.
      </>,
      <>
        Real-time chat with SSE streaming and approval-gated tool calls.
      </>,
      <>Multi-tenant isolation enforced at every storage query.</>,
      <>
        Tests: roughly 750 Python (pytest) and 47 TypeScript (vitest).
      </>,
    ],
  },
];

export default function ChangelogPage() {
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-primary-50/40 to-white">
        <div className="mx-auto w-full max-w-shell px-5 py-20 md:px-8 md:py-24">
          <SectionHeader
            eyebrow="Changelog"
            title="What we've shipped, in reverse chronological order."
            description="No roadmap promises, no marketing copy &mdash; just the concrete increments that have landed on main. Dates use ISO format."
          />
        </div>
      </section>

      <div className="mx-auto w-full max-w-shell px-5 py-16 md:px-8 md:py-24">
        <ol className="flex flex-col gap-10">
          {ENTRIES.map((entry, i) => (
            <li
              key={`${entry.date}-${i}`}
              className="rounded-2xl border border-slate-200 bg-white p-7 shadow-soft-md"
            >
              <div className="flex flex-col gap-1 border-b border-slate-100 pb-4 md:flex-row md:items-baseline md:justify-between md:gap-6">
                <h2 className="text-xl font-bold tracking-tight text-slate-900">
                  <time
                    className="font-mono text-sm font-semibold uppercase tracking-wider text-primary"
                    dateTime={
                      entry.date === "Earlier" ? undefined : entry.date
                    }
                  >
                    {entry.date}
                  </time>
                  <span className="mx-2 text-slate-300">&middot;</span>
                  {entry.title}
                </h2>
              </div>
              <p className="mt-4 text-base leading-relaxed text-slate-700">
                {entry.summary}
              </p>
              <ul className="mt-4 flex list-disc flex-col gap-2 pl-5 text-base leading-relaxed text-slate-700 marker:text-slate-400">
                {entry.bullets.map((bullet, j) => (
                  <li key={j}>{bullet}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>

        <p className="mt-10 text-sm italic text-slate-500">
          For a deeper roadmap see{" "}
          <Link
            href="https://github.com/sumitglobussoft/Voyagent/blob/main/IMPLEMENTATION-PLAN.md"
            className="font-medium text-primary underline"
          >
            IMPLEMENTATION-PLAN.md
          </Link>
          . For architecture decisions see{" "}
          <Link
            href="https://github.com/sumitglobussoft/Voyagent/blob/main/docs/DECISIONS.md"
            className="font-medium text-primary underline"
          >
            docs/DECISIONS.md
          </Link>
          .
        </p>
      </div>

      <CtaBand />
    </>
  );
}
