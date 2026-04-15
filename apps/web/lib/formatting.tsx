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
 * Map a status/kind string to a badge color. Any unknown value falls
 * back to a neutral grey.
 *
 * This map covers three populations:
 *  - approval/enquiry lifecycle statuses (bare words: "pending",
 *    "granted", "booked", …)
 *  - audit-log event kinds (dotted: "approval.granted",
 *    "auth.verify", …) wired in by the approvals → audit hook
 *  - canonical tool names fired through the audit pipeline
 *    ("issue_ticket", "hold_fare", "void_ticket", …) — neutral
 *
 * For dotted audit kinds we also fall back by prefix (``auth.*`` →
 * warning, ``tool.*`` → neutral, ``approval.*`` → grey) so new
 * siblings don't have to be enumerated here to get a sensible color.
 */
const COLOR_WARNING = { bg: "#fef9c3", fg: "#854d0e", border: "#fde68a" };
const COLOR_SUCCESS = { bg: "#dcfce7", fg: "#166534", border: "#bbf7d0" };
const COLOR_DANGER = { bg: "#fee2e2", fg: "#991b1b", border: "#fecaca" };
const COLOR_MUTED = { bg: "#e5e7eb", fg: "#374151", border: "#d1d5db" };
const COLOR_INFO = { bg: "#dbeafe", fg: "#1e40af", border: "#bfdbfe" };
const COLOR_NEUTRAL = { bg: "#f3f4f6", fg: "#374151", border: "#e5e7eb" };

const BADGE_COLORS: Record<string, { bg: string; fg: string; border: string }> = {
  // approvals
  pending: COLOR_WARNING,
  granted: COLOR_SUCCESS,
  rejected: COLOR_DANGER,
  expired: COLOR_MUTED,
  // enquiries
  new: COLOR_INFO,
  quoted: { bg: "#fef3c7", fg: "#92400e", border: "#fde68a" },
  booked: COLOR_SUCCESS,
  cancelled: COLOR_MUTED,
  // audit kinds — approvals → audit hook
  "approval.granted": COLOR_SUCCESS,
  "approval.rejected": COLOR_DANGER,
  "approval.expired": COLOR_MUTED,
  // audit kinds — auth
  "auth.verify": COLOR_WARNING,
  "auth.sign_in": COLOR_SUCCESS,
  // audit kinds — canonical tools (all neutral; the row-level status
  // dot distinguishes ok vs error)
  issue_ticket: COLOR_NEUTRAL,
  hold_fare: COLOR_NEUTRAL,
  void_ticket: COLOR_NEUTRAL,
  refund_ticket: COLOR_NEUTRAL,
};

function resolveBadgeColors(value: string): { bg: string; fg: string; border: string } {
  const hit = BADGE_COLORS[value];
  if (hit) return hit;
  // Prefix fallbacks for dotted audit kinds we haven't enumerated.
  if (value.startsWith("auth.")) return COLOR_WARNING;
  if (value.startsWith("approval.")) return COLOR_MUTED;
  if (value.startsWith("tool.")) return COLOR_NEUTRAL;
  return COLOR_NEUTRAL;
}

export function StatusBadge({ status }: { status: string }): ReactElement {
  const colors = resolveBadgeColors(status);
  // Dotted audit kinds (e.g. ``approval.granted``) are identifiers,
  // not sentences — don't title-case them. Bare lifecycle words like
  // "pending" / "booked" still get capitalized.
  const isDotted = status.includes(".") || status.includes("_");
  const style: CSSProperties = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 999,
    background: colors.bg,
    color: colors.fg,
    border: `1px solid ${colors.border}`,
    fontSize: 12,
    fontWeight: 500,
    textTransform: isDotted ? "none" : "capitalize",
    fontFamily: isDotted
      ? "ui-monospace, SFMono-Regular, Menlo, monospace"
      : undefined,
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
