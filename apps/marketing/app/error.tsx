"use client";

/**
 * Marketing-site global error boundary. Mirrors the web app boundary
 * but uses the marketing palette.
 */
import Link from "next/link";
import { useEffect, type ReactElement } from "react";

export default function MarketingError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): ReactElement {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[voyagent-marketing] error", error);
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
        background: "#ffffff",
        color: "#03161F",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Something went wrong</h1>
      <p style={{ fontSize: 14, maxWidth: 480, color: "#52525b", margin: 0 }}>
        An unexpected error interrupted this page. You can try reloading, or head
        back to the Voyagent home page.
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
            padding: "10px 20px",
            borderRadius: 8,
            background: "#0B4F71",
            color: "#ffffff",
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
            padding: "10px 20px",
            borderRadius: 8,
            border: "1px solid #d4d4d8",
            color: "#03161F",
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
