"use client";

import { useState } from "react";

import { INTEGRATION_LABELS } from "@/lib/site";
import { cn } from "@/lib/cn";

/**
 * Marquee of integration labels.
 *
 * ### Why text and not brand logos?
 * We do not fetch, embed, or distribute real brand logo assets. Many of
 * those marks are trademarked, and unlicensed use on a commercial site
 * risks trademark infringement. Text pills get the same "we integrate with
 * these systems" message without inviting legal pushback or implying an
 * endorsement we don't have.
 *
 * The marquee pauses on hover (respecting `prefers-reduced-motion`
 * globally via the CSS rule in `globals.css`).
 */
export function LogoMarquee() {
  const [paused, setPaused] = useState(false);
  const doubled = [...INTEGRATION_LABELS, ...INTEGRATION_LABELS];
  return (
    <div
      className="group relative overflow-hidden border-y border-slate-200 bg-white py-8"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-white to-transparent"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-white to-transparent"
      />
      <div
        className={cn(
          "flex w-max gap-10 whitespace-nowrap pr-10",
          "animate-marquee",
          paused && "[animation-play-state:paused]",
        )}
        role="list"
        aria-label="Systems Voyagent is built to integrate with"
      >
        {doubled.map((label, idx) => (
          <span
            key={`${label}-${idx}`}
            role="listitem"
            className="flex h-9 items-center rounded-full border border-slate-200 bg-white px-5 text-sm font-medium uppercase tracking-wider text-slate-600"
          >
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
