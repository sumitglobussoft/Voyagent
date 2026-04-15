/**
 * Tiny reusable loading-skeleton primitive.
 *
 * Renders a pulsing neutral block sized by the caller via Tailwind
 * utility classes. Decorative — always ``aria-hidden``.
 */
import type { ReactElement } from "react";

export function Skeleton({ className }: { className?: string }): ReactElement {
  return (
    <div
      className={`animate-pulse rounded bg-neutral-200 ${className ?? ""}`}
      aria-hidden="true"
    />
  );
}

export default Skeleton;
