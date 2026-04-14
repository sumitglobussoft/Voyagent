import { cn } from "@/lib/cn";

export type IntegrationStatus = "full" | "partial" | "planned";

export interface IntegrationBadgeProps {
  label: string;
  status?: IntegrationStatus;
}

const STATUS_STYLES: Record<IntegrationStatus, string> = {
  full: "border-emerald-200 bg-emerald-50 text-emerald-700",
  partial: "border-amber-200 bg-amber-50 text-amber-700",
  planned: "border-slate-200 bg-slate-50 text-slate-600",
};

const STATUS_LABELS: Record<IntegrationStatus, string> = {
  full: "Live",
  partial: "Partial",
  planned: "Planned",
};

/**
 * Integration pill.
 *
 * Used on `/integrations`. Label is text (no brand asset) to avoid
 * trademark/licensing issues while still communicating which systems
 * Voyagent speaks to.
 */
export function IntegrationBadge({
  label,
  status = "planned",
}: IntegrationBadgeProps) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
      <span className="font-medium text-slate-800">{label}</span>
      <span
        className={cn(
          "rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider",
          STATUS_STYLES[status],
        )}
      >
        {STATUS_LABELS[status]}
      </span>
    </div>
  );
}
