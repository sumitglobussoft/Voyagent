/**
 * Authenticated 404 page.
 *
 * Because this file lives under the ``(authed)`` route group, Next
 * wraps it in the authed layout — so signed-in users get the sidebar +
 * mobile header chrome around a friendly not-found message instead of
 * the bare public 404.
 */
import Link from "next/link";
import type { ReactElement } from "react";

export const metadata = {
  title: "Not found — Voyagent",
};

export default function AuthedNotFound(): ReactElement {
  return (
    <main
      role="main"
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
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Page not found</h1>
      <p style={{ fontSize: 14, maxWidth: 420, color: "#71717a", margin: 0 }}>
        The page you were looking for doesn't exist inside Voyagent. Try the
        sidebar, or jump to the main chat workspace.
      </p>
      <Link
        href="/app/chat"
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
        Go to chat
      </Link>
    </main>
  );
}
