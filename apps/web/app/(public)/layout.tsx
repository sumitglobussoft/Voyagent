/**
 * Public (unauthenticated) layout.
 *
 * Used by ``sign-in`` and ``sign-up``. Renders a slim top bar with the
 * Voyagent wordmark on the left and a contextual "Sign in" link on the
 * right (the public pages have their own CTAs for the primary action —
 * the header link is just a fallback for orientation).
 *
 * We don't try to read the current user here; these pages are the
 * unauth flow and a signed-in visitor clicking "Sign in" will be
 * bounced by the middleware anyway.
 */
import type { ReactNode } from "react";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 24px",
          borderBottom: "1px solid #eee",
          background: "#fff",
          height: 56,
          boxSizing: "border-box",
        }}
      >
        {/* Plain anchor (NOT next/link) so basePath isn't auto-prepended.
            The wordmark navigates to the marketing landing at "/". */}
        <a
          href="/"
          style={{
            fontWeight: 700,
            fontSize: 18,
            color: "#111",
            textDecoration: "none",
          }}
        >
          Voyagent
        </a>
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 14 }}>
          <a href="/app/sign-in" style={{ color: "#111" }}>
            Sign in
          </a>
        </div>
      </header>
      {children}
    </>
  );
}
