/**
 * Root layout.
 *
 * Deliberately minimal — just the HTML shell plus the font/background
 * defaults. The actual chrome (sidebar for authenticated routes, top
 * bar for public routes) lives in the route-group layouts under
 * ``(authed)/layout.tsx`` and ``(public)/layout.tsx``.
 */
import type { ReactNode } from "react";

export const metadata = {
  title: "Voyagent",
  description: "Agentic operating system for travel agencies.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#fafafa" }}>
        {children}
      </body>
    </html>
  );
}
