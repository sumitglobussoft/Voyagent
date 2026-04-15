"use client";

/**
 * Thin header strip above the transcript — session title + created-at.
 * The (i) tooltip explains that titles are auto-generated from the
 * first user message so operators aren't surprised.
 */
import type { ReactElement } from "react";

export interface SessionHeaderProps {
  title: string | null;
  createdAt?: string | null;
}

function formatCreatedAt(value: string | null | undefined): string {
  if (!value) return "";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString();
  } catch {
    return "";
  }
}

export function SessionHeader(props: SessionHeaderProps): ReactElement {
  const { title, createdAt } = props;
  const display = title && title.length > 0 ? title : "New chat";
  const isAutoTitle = title !== null && title !== "";
  const formatted = formatCreatedAt(createdAt);

  return (
    <header
      className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 bg-white/90 px-6 py-3 backdrop-blur"
      data-testid="session-header"
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-sm font-semibold text-neutral-900">
          {display}
        </span>
        {isAutoTitle ? (
          <span
            title="Titles are auto-generated from your first message."
            className="cursor-help text-xs text-neutral-400"
            aria-label="Auto-generated title"
          >
            (auto)
          </span>
        ) : null}
      </div>
      {formatted ? (
        <span className="text-xs text-neutral-400">{formatted}</span>
      ) : null}
    </header>
  );
}
