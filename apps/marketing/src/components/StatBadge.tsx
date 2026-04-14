export interface StatBadgeProps {
  label: string;
  value: string;
}

/**
 * Small numeric/fact card used in the landing-page stat strip.
 *
 * Values are phrased modestly — this is a new product, so anything that
 * looks like a volume/usage metric would be a lie. We show scope facts
 * instead ("3 domains", "100+ activities automated").
 */
export function StatBadge({ label, value }: StatBadgeProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="text-2xl font-bold tracking-tight text-primary">
        {value}
      </div>
      <div className="mt-1 text-sm text-slate-600">{label}</div>
    </div>
  );
}
