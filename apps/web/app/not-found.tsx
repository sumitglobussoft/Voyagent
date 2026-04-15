/**
 * Global 404 page (public / unauthenticated).
 *
 * Next 15 renders this automatically when a route segment calls
 * `notFound()` or when no segment matches the requested URL. The authed
 * route group owns its own `not-found.tsx` so signed-in users see the
 * sidebar chrome instead of this bare page.
 */
import Link from "next/link";
import type { ReactElement } from "react";

export const metadata = {
  title: "Page not found — Voyagent",
};

export default function NotFound(): ReactElement {
  return (
    <main
      role="main"
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
      <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Page not found</h1>
      <p style={{ fontSize: 14, maxWidth: 420, color: "var(--voyagent-muted, #71717a)", margin: 0 }}>
        We couldn't find what you were looking for. Check the URL, or head back to
        the Voyagent home page.
      </p>
      <Link
        href="/"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 16px",
          borderRadius: 8,
          background: "#18181b",
          color: "#fafafa",
          textDecoration: "none",
          fontSize: 14,
          fontWeight: 500,
        }}
      >
        Go home
      </Link>
    </main>
  );
}
