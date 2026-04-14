import type { ComponentType, SVGProps } from "react";

export interface FeatureGridItem {
  title: string;
  description: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
}

export interface FeatureGridProps {
  items: FeatureGridItem[];
  columns?: 2 | 3 | 4;
}

/**
 * Configurable grid of feature cards.
 *
 * Used on `/features` and on domain pages. Icons come from
 * `@voyagent/icons` (a curated Lucide subset) so we stay visually
 * consistent with the product UI.
 */
export function FeatureGrid({ items, columns = 3 }: FeatureGridProps) {
  const gridCols =
    columns === 4
      ? "md:grid-cols-2 lg:grid-cols-4"
      : columns === 2
        ? "md:grid-cols-2"
        : "md:grid-cols-2 lg:grid-cols-3";
  return (
    <div className={`grid gap-6 ${gridCols}`}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div
            key={item.title}
            className="rounded-xl border border-slate-200 bg-white p-6 shadow-soft-md transition hover:border-primary-200 hover:shadow-soft-lg"
          >
            {Icon ? (
              <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary">
                <Icon width={20} height={20} aria-hidden="true" />
              </div>
            ) : null}
            <h3 className="text-lg font-semibold tracking-tight text-slate-900">
              {item.title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              {item.description}
            </p>
          </div>
        );
      })}
    </div>
  );
}
