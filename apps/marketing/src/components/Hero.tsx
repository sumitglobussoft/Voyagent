import Link from "next/link";

/**
 * Landing-page hero.
 *
 * The radial glow behind the headline is a pure CSS gradient (no image) so
 * no network asset is needed and color-theme changes are one variable away.
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
        <h1 className="mt-6 max-w-4xl text-4xl font-bold tracking-tighter text-slate-900 md:text-6xl">
          One chat. Every GDS, every accounting system, every workflow.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-600 md:text-xl">
          Voyagent replaces the 8&ndash;15 tools a travel agency juggles every
          day with a single chat interface, backed by AI agents that plan,
          quote, book, invoice and reconcile across the vendors you already
          use.
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
            Explore the product
          </Link>
        </div>
        <p className="mt-6 text-sm text-slate-500">
          In early access. India-first. Global-ready architecture.
        </p>
      </div>
    </section>
  );
}
