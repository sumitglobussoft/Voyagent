import { forwardRef, type HTMLAttributes, type ReactNode } from "react";

import { cn } from "./cn.js";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  header?: ReactNode;
  footer?: ReactNode;
  /** Remove internal body padding (useful when embedding tables/lists). */
  flush?: boolean;
}

/**
 * Plain container with optional header + footer slots. Stateless, purely
 * cosmetic. Consumers can pass any `div` props including `role="region"`
 * and `aria-labelledby` to make it a landmark.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { header, footer, flush = false, className, children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        "flex flex-col rounded-lg border border-neutral-200 bg-white shadow-sm",
        className,
      )}
      {...rest}
    >
      {header !== undefined ? (
        <div className="border-b border-neutral-200 px-4 py-3 text-sm font-medium text-neutral-800">
          {header}
        </div>
      ) : null}
      <div className={cn("flex-1", flush ? "" : "p-4")}>{children}</div>
      {footer !== undefined ? (
        <div className="border-t border-neutral-200 px-4 py-3 text-sm text-neutral-600">
          {footer}
        </div>
      ) : null}
    </div>
  );
});
