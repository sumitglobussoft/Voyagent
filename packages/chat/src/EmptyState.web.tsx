"use client";

/**
 * Empty state rendered when a brand-new session has no messages yet.
 *
 * Four example prompt cards seed the composer on click — they do NOT
 * auto-submit, on the theory that operators should always review the
 * text before sending.
 */
import type { ReactElement } from "react";

export interface EmptyStateProps {
  onPick: (text: string) => void;
}

// Domain-leaning examples: flights, ticketing, accounting, enquiries —
// one per major workflow the agent is expected to cover.
export const SUGGESTIONS: ReadonlyArray<string> = [
  "Find me a Delhi to Dubai flight for next Friday",
  "Issue a ticket for PNR ABC123",
  "Show me last month's receivables aging",
  "Draft an enquiry for Mr. Sharma — 5 nights in Bangkok",
];

export function EmptyState({ onPick }: EmptyStateProps): ReactElement {
  return (
    <div
      className="flex flex-1 flex-col items-center justify-center gap-10 px-6 py-12"
      data-testid="empty-state"
    >
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-neutral-900 to-neutral-700 text-white shadow-sm">
          <span className="text-xl font-semibold tracking-tight">V</span>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-neutral-900">
          How can I help today?
        </h1>
        <p className="max-w-md text-sm text-neutral-500">
          Ask about flights, hotels, enquiries, approvals, or your agency&apos;s books.
          Pick a suggestion below or type your own.
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="group rounded-xl border border-neutral-200 bg-white p-4 text-left text-sm text-neutral-700 shadow-sm transition hover:-translate-y-px hover:border-neutral-300 hover:shadow-md"
          >
            <span className="block text-xs font-medium uppercase tracking-wide text-neutral-400 group-hover:text-neutral-500">
              Try
            </span>
            <span className="mt-1 block leading-snug text-neutral-800">{s}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
