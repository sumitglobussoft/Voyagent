import { forwardRef, type HTMLAttributes, type ReactNode } from "react";

import { cn } from "./cn.js";

export interface EmptyStateProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Optional call-to-action (typically a <Button>). */
  action?: ReactNode;
}

/**
 * Placeholder shown when a surface has nothing to display yet — e.g.
 * the Reports tab before any reports exist, or the mobile "coming soon"
 * screens.
 */
export const EmptyState = forwardRef<HTMLDivElement, EmptyStateProps>(
  function EmptyState(
    { icon, title, description, action, className, ...rest },
    ref,
  ) {
    return (
      <div
        ref={ref}
        role="status"
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-neutral-300 bg-neutral-50 p-8 text-center",
          className,
        )}
        {...rest}
      >
        {icon !== undefined ? (
          <div className="text-neutral-400" aria-hidden="true">
            {icon}
          </div>
        ) : null}
        <div className="text-base font-semibold text-neutral-800">{title}</div>
        {description !== undefined ? (
          <div className="max-w-prose text-sm text-neutral-600">
            {description}
          </div>
        ) : null}
        {action !== undefined ? <div className="mt-2">{action}</div> : null}
      </div>
    );
  },
);
