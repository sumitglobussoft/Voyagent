/**
 * Honest testimonial placeholder.
 *
 * We don't have customer quotes yet. Rather than mocking up fake praise,
 * we show a placeholder that tells visitors exactly where we are in the
 * product cycle. This stays here until we have explicit written consent
 * from early-access tenants to attribute quotes.
 */
export function TestimonialPlaceholder() {
  return (
    <section className="mx-auto w-full max-w-shell px-5 py-16 md:px-8 md:py-24">
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
        <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Testimonials
        </div>
        <h2 className="mt-3 text-2xl font-bold tracking-tighter text-slate-900">
          Coming soon.
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-base text-slate-600">
          Our first early-access agencies are onboarding now. We&rsquo;ll
          share quotes here only when they&rsquo;re real, consented, and
          attributable &mdash; not before.
        </p>
      </div>
    </section>
  );
}
