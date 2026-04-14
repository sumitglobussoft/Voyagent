import Link from "next/link";

/**
 * Landing-page hero.
 *
 * The radial glow behind the headline is a pure CSS gradient (no image) so
 * no network asset is needed and color-theme changes are one variable
 * away. Copy is deliberately conservative — we sell the product on
 * mechanism, not adjectives.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-slate-200 bg-white">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-hero-glow"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 left-1/2 h-96 w-[900px] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl"
      />
      <div className="relative mx-auto flex w-full max-w-shell flex-col items-center px-5 py-20 text-center md:px-8 md:py-28">
        <span className="inline-flex items-center rounded-full border border-primary-100 bg-primary-50 px-4 py-1.5 text-xs font-medium uppercase tracking-widest text-primary">
          The Agentic Travel OS
        </span>
        <h1 className="mt-6 max-w-4xl text-4xl font-bold tracking-tighter text-slate-900 md:text-[3.75rem] md:leading-[1.05]">
          Run your travel agency from one chat.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-600 md:text-xl">
          Voyagent is an agentic operating system that collapses the eight
          to fifteen tools your team touches every day &mdash; GDS,
          consolidators, hotel banks, visa portals, payment rails,
          accounting &mdash; into one conversation. Your staff ask; Voyagent
          quotes, books, invoices and reconciles, with human approval on
          every irreversible step.
        </p>

        <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row">
          <Link
            href="/#cta"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-base font-semibold text-white shadow-soft-lg transition hover:bg-primary-600"
          >
            Request early access
          </Link>
          <Link
            href="/product"
            className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-6 py-3 text-base font-semibold text-slate-800 transition hover:border-primary hover:text-primary"
          >
            See the product
          </Link>
        </div>

        <dl className="mt-12 grid w-full max-w-3xl grid-cols-2 gap-6 border-t border-slate-200 pt-10 text-left md:grid-cols-4">
          <HeroStat value="1 chat" label="Replaces 8&ndash;15 tools" />
          <HeroStat value="3 domains" label="Ticketing, Hotels, Accounting" />
          <HeroStat value="Vendor-agnostic" label="By architecture" />
          <HeroStat value="Audit-ready" label="Approvals on every side-effect" />
        </dl>
      </div>
    </section>
  );
}

function HeroStat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        <span dangerouslySetInnerHTML={{ __html: label }} />
      </dt>
      <dd className="mt-1 text-lg font-semibold text-slate-900">{value}</dd>
    </div>
  );
}
