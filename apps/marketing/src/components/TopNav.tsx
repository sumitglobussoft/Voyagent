"use client";

import Link from "next/link";
import { useState } from "react";

import { NAV_LINKS, SITE } from "@/lib/site";
import { cn } from "@/lib/cn";

/**
 * Responsive top navigation.
 *
 * Client component because it owns the mobile-drawer disclosure state.
 * Primary CTA sends users to the product shell at `/app` (served by the
 * reverse proxy); secondary CTA jumps to the in-page #cta band.
 */
export function TopNav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-shell items-center justify-between px-5 md:px-8">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight"
          aria-label={`${SITE.name} home`}
        >
          <WordMark />
        </Link>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-7 md:flex"
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-slate-600 transition hover:text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href={SITE.appUrl}
            className="text-sm font-medium text-slate-700 transition hover:text-primary"
          >
            Sign in
          </Link>
          <Link
            href="/#cta"
            className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white shadow-soft-md transition hover:bg-primary-600"
          >
            Request early access
          </Link>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
          className="rounded-md p-2 text-slate-700 md:hidden"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {open ? (
              <>
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>
      </div>

      <div
        id="mobile-nav"
        className={cn(
          "overflow-hidden border-t border-slate-200 md:hidden",
          open ? "block" : "hidden",
        )}
      >
        <nav aria-label="Mobile" className="flex flex-col gap-1 px-5 py-4">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="rounded px-2 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              {link.label}
            </Link>
          ))}
          <div className="mt-2 flex items-center gap-3 border-t border-slate-200 pt-3">
            <Link
              href={SITE.appUrl}
              className="flex-1 rounded-md border border-slate-200 px-3 py-2 text-center text-sm font-medium text-slate-700"
            >
              Sign in
            </Link>
            <Link
              href="/#cta"
              onClick={() => setOpen(false)}
              className="flex-1 rounded-md bg-primary px-3 py-2 text-center text-sm font-semibold text-white"
            >
              Request early access
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}

function WordMark() {
  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary text-[12px] font-bold text-white"
      >
        V
      </span>
      <span className="text-[17px] tracking-tight">Voyagent</span>
    </span>
  );
}
