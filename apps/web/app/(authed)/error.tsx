"use client";

/**
 * Error boundary for the authenticated route group. Catches thrown
 * errors inside any `(authed)/*` page and renders them inside the
 * sidebar chrome so the user still has navigation available.
 */
import { useEffect, type ReactElement } from "react";

export default function AuthedError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): ReactElement {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[voyagent] authed route error", error);
  }, [error]);

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <main
      role="main"
      data-testid="authed-error-boundary"
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        textAlign: "center",
        gap: 16,
      }}
    >
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>
        This page hit a snag
      </h1>
      <p style={{ fontSize: 14, maxWidth: 420, color: "#71717a", margin: 0 }}>
        Something went wrong loading this view. Try reloading — your session is
        still active.
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
    </main>
  );
}
