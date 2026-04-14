import { forwardRef, type HTMLAttributes } from "react";

import { cn } from "./cn.js";

export type SpinnerSize = "sm" | "md" | "lg";

export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  size?: SpinnerSize;
  /** Accessible label announced to screen readers. Defaults to "Loading". */
  label?: string;
}

const SIZE: Record<SpinnerSize, string> = {
  sm: "h-3 w-3 border-2",
  md: "h-4 w-4 border-2",
  lg: "h-6 w-6 border-[3px]",
};

/**
 * Indeterminate CSS spinner. Pure Tailwind — consumers must have the
 * Tailwind `animate-spin` utility available (it ships in default Tailwind).
 */
export const Spinner = forwardRef<HTMLSpanElement, SpinnerProps>(
  function Spinner(
    { size = "md", label = "Loading", className, ...rest },
    ref,
  ) {
    return (
      <span
        ref={ref}
        role="status"
        aria-live="polite"
        className={cn("inline-flex items-center", className)}
        {...rest}
      >
        <span
          aria-hidden="true"
          className={cn(
            "inline-block animate-spin rounded-full border-solid border-current border-r-transparent",
            SIZE[size],
          )}
        />
        <span className="sr-only">{label}</span>
      </span>
    );
  },
);
