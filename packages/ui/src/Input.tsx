import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

import { cn } from "./cn.js";

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: ReactNode;
  description?: ReactNode;
  /** Error message — when set, the field is styled as invalid and `aria-invalid` is set. */
  error?: ReactNode;
  required?: boolean;
}

/**
 * Labeled text input with description + error slots. Generates a stable id
 * via `useId` and wires the `<label>` / `aria-describedby` / `aria-invalid`
 * bindings for accessibility.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, description, error, required, id, className, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const descId = description ? `${inputId}-desc` : undefined;
  const errId = error ? `${inputId}-err` : undefined;
  const describedBy =
    [descId, errId].filter((v): v is string => Boolean(v)).join(" ") ||
    undefined;

  return (
    <div className="flex w-full flex-col gap-1">
      {label !== undefined ? (
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-neutral-800"
        >
          {label}
          {required ? (
            <span aria-hidden="true" className="ml-0.5 text-red-600">
              *
            </span>
          ) : null}
        </label>
      ) : null}
      <input
        id={inputId}
        ref={ref}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        aria-required={required || undefined}
        required={required}
        className={cn(
          "h-10 rounded-md border bg-white px-3 text-sm text-neutral-900",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1",
          "disabled:cursor-not-allowed disabled:opacity-60",
          error
            ? "border-red-400 focus-visible:ring-red-400"
            : "border-neutral-300 focus-visible:ring-neutral-400",
          className,
        )}
        {...rest}
      />
      {description && !error ? (
        <p id={descId} className="text-xs text-neutral-500">
          {description}
        </p>
      ) : null}
      {error ? (
        <p id={errId} role="alert" className="text-xs text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
});
