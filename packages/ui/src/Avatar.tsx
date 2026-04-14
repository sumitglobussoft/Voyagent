import { forwardRef, useState, type HTMLAttributes } from "react";

import { cn } from "./cn.js";

export type AvatarSize = "sm" | "md" | "lg";

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  /** Image source. If omitted or it fails to load, we fall back to initials. */
  src?: string;
  /** Full name or label used to derive initials when `src` is missing. */
  name: string;
  size?: AvatarSize;
  /** Alt text override. Defaults to `name`. */
  alt?: string;
}

const SIZE: Record<AvatarSize, string> = {
  sm: "h-6 w-6 text-[10px]",
  md: "h-8 w-8 text-xs",
  lg: "h-10 w-10 text-sm",
};

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1] ?? "") : "";
  const a = first.charAt(0);
  const b = last.charAt(0);
  return (a + b).toUpperCase() || "?";
}

export const Avatar = forwardRef<HTMLSpanElement, AvatarProps>(function Avatar(
  { src, name, size = "md", alt, className, ...rest },
  ref,
) {
  const [failed, setFailed] = useState(false);
  const showImage = src !== undefined && src.length > 0 && !failed;

  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center overflow-hidden rounded-full bg-neutral-200 font-medium text-neutral-700",
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {showImage ? (
        <img
          src={src}
          alt={alt ?? name}
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <span aria-label={alt ?? name}>{initialsOf(name)}</span>
      )}
    </span>
  );
});
