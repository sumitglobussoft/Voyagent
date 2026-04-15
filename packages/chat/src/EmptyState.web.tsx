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
      className="flex flex-1 flex-col items-center justify-center gap-6 p-8"
      data-testid="empty-state"
    >
      <h1 className="text-2xl font-semibold text-neutral-800">
        How can I help today?
      </h1>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="rounded-lg border border-neutral-200 bg-white p-4 text-left text-sm text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
