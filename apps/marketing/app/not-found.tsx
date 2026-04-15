/**
 * Marketing-site 404. Matches the marketing visual system (teal primary
 * accent, generous whitespace) rather than the app's neutral chrome.
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
        background: "#ffffff",
        color: "#03161F",
      }}
    >
      <div
        aria-hidden
        style={{
          fontSize: 48,
          fontWeight: 700,
          letterSpacing: -2,
          color: "#0B4F71",
        }}
      >
        404
      </div>
      <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Page not found</h1>
      <p style={{ fontSize: 14, maxWidth: 480, color: "#52525b", margin: 0 }}>
        We couldn't find the page you were looking for. The link may be stale, or
        the page may have moved.
      </p>
      <Link
        href="/"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 20px",
          borderRadius: 8,
          background: "#0B4F71",
          color: "#ffffff",
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
