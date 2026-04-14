/**
 * Root layout.
 *
 * Renders a small top bar with the wordmark on the left and (server-side)
 * either the current user + sign-out form or a sign-in link on the right.
 *
 * No client-side auth provider — all session reads happen in server
 * components via `lib/auth.ts`.
 */
import type { ReactNode } from "react";
import Link from "next/link";

import { getCurrentUser } from "@/lib/auth";

export const metadata = {
  title: "Voyagent",
  description: "Agentic operating system for travel agencies.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();

  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#fafafa" }}>
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
          <Link
            href="/"
            style={{
              fontWeight: 700,
              fontSize: 18,
              color: "#111",
              textDecoration: "none",
            }}
          >
            Voyagent
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 14 }}>
            {user ? (
              <>
                <span style={{ color: "#444" }}>
                  {user.full_name ?? user.email}
                  <span style={{ color: "#888" }}> · {user.tenant_name}</span>
                </span>
                <form action="/app/sign-out" method="post" style={{ margin: 0 }}>
                  <button
                    type="submit"
                    style={{
                      background: "transparent",
                      border: "1px solid #d4d4d8",
                      borderRadius: 6,
                      padding: "6px 12px",
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    Sign out
                  </button>
                </form>
              </>
            ) : (
              <Link href="/sign-in" style={{ color: "#111" }}>
                Sign in
              </Link>
            )}
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
