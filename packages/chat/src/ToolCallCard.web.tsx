"use client";

/**
 * Collapsible tool-call card.
 *
 * Uses a native `<details>` / `<summary>` so keyboard accessibility, the
 * open-on-enter behavior, and the disclosure affordance come for free.
 * Derives a short one-line summary from the tool input where we can
 * recognize the shape (flight search, PNR lookup, …); otherwise just
 * shows the tool name.
 */
import type { ReactElement } from "react";

import type { ToolCallEntry } from "./types.js";

export interface ToolCallCardProps {
  call: ToolCallEntry;
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Derive a human-readable one-line description from the tool args.
 * Falls back to an empty string if we don't recognize the shape — the
 * caller renders only the tool name in that case.
 */
function deriveSummary(
  toolName: string,
  input: Record<string, unknown>,
): string {
  const pick = (k: string): string | undefined => {
    const v = input[k];
    return typeof v === "string" ? v : undefined;
  };

  // Flight searches — the workhorse for this agent.
  if (toolName.includes("flight") || toolName.includes("search_flights")) {
    const o = pick("origin") ?? pick("from") ?? pick("from_iata");
    const d = pick("destination") ?? pick("to") ?? pick("to_iata");
    if (o && d) return `${o} -> ${d}`;
  }

  // PNR / ticket operations.
  const pnr = pick("pnr") ?? pick("record_locator");
  if (pnr) return `PNR ${pnr}`;

  // Invoice / receivables.
  const invoice = pick("invoice_id");
  if (invoice) return `invoice ${invoice}`;

  return "";
}

function statusDot(call: ToolCallEntry): ReactElement {
  if (!call.done) {
    return (
      <span
        aria-label="running"
        className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500"
      />
    );
  }
  const isError =
    call.tool_output !== undefined &&
    typeof call.tool_output === "object" &&
    call.tool_output !== null &&
    "error" in (call.tool_output as Record<string, unknown>);
  return (
    <span
      aria-label={isError ? "error" : "ok"}
      className={`inline-block h-2 w-2 rounded-full ${
        isError ? "bg-red-500" : "bg-emerald-500"
      }`}
    />
  );
}

export function ToolCallCard({ call }: ToolCallCardProps): ReactElement {
  const summary = deriveSummary(call.tool_name, call.tool_input);

  return (
    <details
      className="my-2 rounded border border-neutral-300 bg-neutral-50 text-sm text-neutral-800"
      data-testid="tool-card"
    >
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2">
        {statusDot(call)}
        <span className="rounded bg-neutral-200 px-1.5 py-0.5 text-xs font-mono uppercase tracking-wide text-neutral-700">
          {call.tool_name}
        </span>
        {summary ? (
          <span className="text-xs text-neutral-600">{summary}</span>
        ) : null}
      </summary>
      <div className="border-t border-neutral-200 px-3 py-2">
        <div className="mb-1 text-xs uppercase tracking-wide text-neutral-500">
          Arguments
        </div>
        <pre className="overflow-x-auto rounded bg-neutral-100 p-2 text-xs">
          {prettyJson(call.tool_input)}
        </pre>
        {call.tool_output !== undefined ? (
          <div data-testid="tool-card-result">
            <div className="mb-1 mt-3 flex items-center gap-2 text-xs uppercase tracking-wide text-neutral-500">
              Result {statusDot(call)}
            </div>
            <pre className="overflow-x-auto rounded bg-neutral-100 p-2 text-xs">
              {prettyJson(call.tool_output)}
            </pre>
          </div>
        ) : null}
      </div>
    </details>
  );
}
