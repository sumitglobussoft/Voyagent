import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface SectionHeaderProps {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  align?: "left" | "center";
  className?: string;
}

/**
 * Reusable section heading.
 *
 * Usage: at the top of every marketing section to give the page a clear,
 * scan-friendly visual hierarchy (eyebrow tag → H2 → lede paragraph).
 */
export function SectionHeader({
  eyebrow,
  title,
  description,
  align = "left",
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        align === "center" ? "items-center text-center" : "items-start",
        className,
      )}
    >
      {eyebrow ? (
        <span className="inline-flex items-center rounded-full bg-primary-50 px-3 py-1 text-xs font-medium uppercase tracking-widest text-primary">
          {eyebrow}
        </span>
      ) : null}
      <h2 className="max-w-3xl text-3xl font-bold tracking-tighter text-slate-900 md:text-4xl">
        {title}
      </h2>
      {description ? (
        <p className="max-w-2xl text-base leading-relaxed text-slate-600 md:text-lg">
          {description}
        </p>
      ) : null}
    </div>
  );
}
