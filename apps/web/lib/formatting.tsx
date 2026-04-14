import "server-only";

import type { CSSProperties, ReactElement } from "react";

/**
 * Formatting helpers shared across the approvals and enquiries pages.
 *
 * Everything here is pure — no data fetching, no cookies. Kept in
 * `lib/` so the pages don't invent private copies of the same
 * logic.
 */

const DATE_FMT = new Intl.DateTimeFormat("en-IN", {
  year: "numeric",
  month: "short",
  day: "2-digit",
});

const DATETIME_FMT = new Intl.DateTimeFormat("en-IN", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return DATE_FMT.format(d);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return DATETIME_FMT.format(d);
}

/**
 * Relative time: "5 min ago", "in 9 min", "just now", "3 hr ago".
 * Coarse-grained — no seconds, no "yesterday" magic.
 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const deltaMs = d.getTime() - Date.now();
  const absMs = Math.abs(deltaMs);
  const mins = Math.round(absMs / 60_000);
  const future = deltaMs > 0;

  if (absMs < 30_000) return "just now";
  if (mins < 60) {
    return future ? `in ${mins} min` : `${mins} min ago`;
  }
  const hrs = Math.round(mins / 60);
  if (hrs < 24) {
    return future ? `in ${hrs} hr` : `${hrs} hr ago`;
  }
  const days = Math.round(hrs / 24);
  if (days < 30) {
    return future ? `in ${days} d` : `${days} d ago`;
  }
  return formatDate(iso);
}

/**
 * Has the timestamp already passed?
 */
export function isPast(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  return d.getTime() < Date.now();
}

/**
 * Map a status string to a badge color. Any unknown status falls back
 * to a neutral grey.
 */
const BADGE_COLORS: Record<string, { bg: string; fg: string; border: string }> = {
  // approvals
  pending: { bg: "#fef9c3", fg: "#854d0e", border: "#fde68a" },
  granted: { bg: "#dcfce7", fg: "#166534", border: "#bbf7d0" },
  rejected: { bg: "#fee2e2", fg: "#991b1b", border: "#fecaca" },
  expired: { bg: "#e5e7eb", fg: "#374151", border: "#d1d5db" },
  // enquiries
  new: { bg: "#dbeafe", fg: "#1e40af", border: "#bfdbfe" },
  quoted: { bg: "#fef3c7", fg: "#92400e", border: "#fde68a" },
  booked: { bg: "#dcfce7", fg: "#166534", border: "#bbf7d0" },
  cancelled: { bg: "#e5e7eb", fg: "#374151", border: "#d1d5db" },
};

export function StatusBadge({ status }: { status: string }): ReactElement {
  const colors = BADGE_COLORS[status] ?? {
    bg: "#f3f4f6",
    fg: "#374151",
    border: "#e5e7eb",
  };
  const style: CSSProperties = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 999,
    background: colors.bg,
    color: colors.fg,
    border: `1px solid ${colors.border}`,
    fontSize: 12,
    fontWeight: 500,
    textTransform: "capitalize",
    whiteSpace: "nowrap",
  };
  return <span style={style}>{status}</span>;
}

export function truncate(s: string, max = 12): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

export function formatBudget(
  amount: string | null | undefined,
  currency: string | null | undefined,
): string {
  if (!amount) return "—";
  if (!currency) return amount;
  return `${amount} ${currency}`;
}
