import Link from "next/link";

import { FOOTER_LINKS, SITE } from "@/lib/site";

/**
 * Site footer with three link columns and a non-affiliation disclaimer.
 *
 * Named-group columns come from `FOOTER_LINKS` in `lib/site.ts` so copy
 * updates happen in one place.
 */
export function Footer() {
  return (
    <footer className="mt-24 border-t border-slate-200 bg-slate-50">
      <div className="mx-auto grid w-full max-w-shell gap-10 px-5 py-14 md:grid-cols-5 md:px-8">
        <div className="md:col-span-2">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <span
              aria-hidden="true"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary text-[12px] font-bold text-white"
            >
              V
            </span>
            <span>{SITE.name}</span>
          </div>
          <p className="mt-3 max-w-sm text-sm text-slate-600">
            {SITE.category}. {SITE.tagline}
          </p>
          <p className="mt-6 text-xs leading-relaxed text-slate-500">
            Voyagent is not affiliated with, endorsed by, or sponsored by any
            GDS, airline, hotel chain, accounting software vendor, visa
            portal, or bank. All trademarks belong to their respective
            owners.
          </p>
        </div>
        {Object.entries(FOOTER_LINKS).map(([heading, items]) => (
          <div key={heading}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {heading}
            </h4>
            <ul className="mt-4 space-y-2">
              {items.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-sm text-slate-700 transition hover:text-primary"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200">
        <div className="mx-auto flex w-full max-w-shell flex-col items-start justify-between gap-2 px-5 py-5 text-xs text-slate-500 md:flex-row md:items-center md:px-8">
          <span>
            &copy; {new Date().getFullYear()} {SITE.name}. All rights reserved.
          </span>
          <span>India-first. Global-ready.</span>
        </div>
      </div>
    </footer>
  );
}
