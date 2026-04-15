"use client";

/**
 * Global error boundary (public).
 *
 * Next 15 renders this when a route throws and no nested `error.tsx`
 * catches it first. Must be a Client Component per the Next spec.
 * Shows a friendly message, a reload button, and — in development — the
 * error digest to help debugging.
 */
import Link from "next/link";
import { useEffect, type ReactElement } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): ReactElement {
  useEffect(() => {
    // Fire-and-forget: the parent `instrumentation.ts` wires Sentry,
    // which will pick this up automatically. Keep a console line too
    // so local dev sees the trace even without devtools open.
    // eslint-disable-next-line no-console
    console.error("[voyagent] route error", error);
  }, [error]);

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <main
      role="main"
      data-testid="error-boundary"
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        textAlign: "center",
        gap: 16,
        background: "var(--voyagent-bg, #fafafa)",
        color: "var(--voyagent-fg, #18181b)",
      }}
    >
      <div
        aria-hidden
        style={{
          width: 56,
          height: 56,
          borderRadius: 12,
          background: "linear-gradient(135deg, #18181b, #3f3f46)",
          color: "#fafafa",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 28,
          fontWeight: 700,
          letterSpacing: -1,
        }}
      >
        V
      </div>
      <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Something went wrong</h1>
      <p style={{ fontSize: 14, maxWidth: 420, color: "var(--voyagent-muted, #71717a)", margin: 0 }}>
        An unexpected error interrupted this page. You can try reloading, or head
        back home if the problem persists.
      </p>
      {isDev && error.digest ? (
        <code
          style={{
            fontSize: 12,
            padding: "4px 8px",
            background: "#f4f4f5",
            borderRadius: 4,
            color: "#52525b",
          }}
        >
          digest: {error.digest}
        </code>
      ) : null}
      <div style={{ display: "inline-flex", gap: 8 }}>
        <button
          type="button"
          onClick={reset}
          style={{
            padding: "8px 16px",
            borderRadius: 8,
            background: "#18181b",
            color: "#fafafa",
            border: "none",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          Reload
        </button>
        <Link
          href="/"
          style={{
            padding: "8px 16px",
            borderRadius: 8,
            border: "1px solid #d4d4d8",
            color: "#18181b",
            textDecoration: "none",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          Go home
        </Link>
      </div>
    </main>
  );
}
