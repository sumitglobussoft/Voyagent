"use client";

/**
 * Collapsible card summarizing a single tool_use → tool_result pair.
 * Minimal, unobtrusive — the goal is letting operators audit what the agent
 * did without dragging their eye away from the conversation.
 */
import { useState, type ReactElement } from "react";

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

export function ToolCallCard({ call }: ToolCallCardProps): ReactElement {
  const [open, setOpen] = useState(false);

  const status = call.done ? "done" : "running";

  return (
    <div
      className="my-2 rounded border border-neutral-300 bg-neutral-50 text-sm text-neutral-800"
      role="group"
      aria-label={`Tool call ${call.tool_name}`}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-mono">
          {call.tool_name}
          <span className="ml-2 text-xs text-neutral-500">({status})</span>
        </span>
        <span aria-hidden="true" className="text-neutral-500">
          {open ? "-" : "+"}
        </span>
      </button>
      {open ? (
        <div className="border-t border-neutral-200 px-3 py-2">
          <div className="mb-1 text-xs uppercase tracking-wide text-neutral-500">
            Input
          </div>
          <pre className="overflow-x-auto rounded bg-neutral-100 p-2 text-xs">
            {prettyJson(call.tool_input)}
          </pre>
          {call.tool_output !== undefined ? (
            <>
              <div className="mb-1 mt-3 text-xs uppercase tracking-wide text-neutral-500">
                Output
              </div>
              <pre className="overflow-x-auto rounded bg-neutral-100 p-2 text-xs">
                {prettyJson(call.tool_output)}
              </pre>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
