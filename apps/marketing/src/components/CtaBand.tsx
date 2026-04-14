import Link from "next/link";

/**
 * Pre-footer call-to-action band.
 *
 * Lives at `#cta` so the nav's secondary CTA and hero buttons can scroll
 * here without leaving the landing page.
 */
export function CtaBand() {
  return (
    <section
      id="cta"
      aria-labelledby="cta-heading"
      className="relative overflow-hidden bg-primary text-white"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-20 top-1/2 h-80 w-80 -translate-y-1/2 rounded-full bg-primary-400/30 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-20 top-1/2 h-80 w-80 -translate-y-1/2 rounded-full bg-accent/25 blur-3xl"
      />
      <div className="relative mx-auto flex w-full max-w-shell flex-col items-start justify-between gap-8 px-5 py-16 md:flex-row md:items-center md:px-8 md:py-20">
        <div>
          <h2
            id="cta-heading"
            className="max-w-2xl text-3xl font-bold tracking-tighter md:text-4xl"
          >
            Ready to retire the 15-tool workflow?
          </h2>
          <p className="mt-3 max-w-xl text-base text-primary-100 md:text-lg">
            Voyagent is in early access. We onboard a small number of
            agencies each month with white-glove setup of drivers, data, and
            approval workflows.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            href="/contact"
            className="inline-flex items-center justify-center rounded-md bg-white px-6 py-3 text-base font-semibold text-primary shadow-soft-md transition hover:bg-primary-50"
          >
            Request early access
          </Link>
          <Link
            href="/product"
            className="inline-flex items-center justify-center rounded-md border border-white/30 px-6 py-3 text-base font-semibold text-white transition hover:bg-white/10"
          >
            See a walkthrough
          </Link>
        </div>
      </div>
    </section>
  );
}
