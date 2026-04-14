import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useId,
  type TextareaHTMLAttributes,
  type ReactNode,
} from "react";

import { cn } from "./cn.js";

export interface TextAreaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  description?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  /** Maximum auto-grow height in pixels. Defaults to 240. */
  maxHeight?: number;
}

/**
 * Multi-line text input that grows with its content up to `maxHeight`
 * (pixels). Above that, scroll. Uses the value/defaultValue to detect
 * content changes rather than listening to `input`.
 */
export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea(
    {
      label,
      description,
      error,
      required,
      maxHeight = 240,
      id,
      className,
      value,
      defaultValue,
      onChange,
      ...rest
    },
    forwardedRef,
  ) {
    const generatedId = useId();
    const fieldId = id ?? generatedId;
    const descId = description ? `${fieldId}-desc` : undefined;
    const errId = error ? `${fieldId}-err` : undefined;
    const describedBy =
      [descId, errId].filter((v): v is string => Boolean(v)).join(" ") ||
      undefined;

    const innerRef = useRef<HTMLTextAreaElement | null>(null);
    useImperativeHandle(
      forwardedRef,
      () => innerRef.current as HTMLTextAreaElement,
    );

    const autoSize = useCallback(() => {
      const el = innerRef.current;
      if (!el) return;
      el.style.height = "auto";
      const target = Math.min(el.scrollHeight, maxHeight);
      el.style.height = `${target}px`;
      el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
    }, [maxHeight]);

    useEffect(() => {
      autoSize();
    }, [autoSize, value]);

    return (
      <div className="flex w-full flex-col gap-1">
        {label !== undefined ? (
          <label
            htmlFor={fieldId}
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
        <textarea
          id={fieldId}
          ref={innerRef}
          value={value}
          defaultValue={defaultValue}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          required={required}
          rows={1}
          onChange={(ev) => {
            onChange?.(ev);
            autoSize();
          }}
          className={cn(
            "min-h-[2.5rem] resize-none rounded-md border bg-white px-3 py-2 text-sm text-neutral-900",
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
  },
);
