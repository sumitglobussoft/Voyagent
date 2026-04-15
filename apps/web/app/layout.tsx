/**
 * Root layout.
 *
 * Deliberately minimal — just the HTML shell, Tailwind base styles, and
 * the font defaults. The actual chrome (sidebar for authenticated
 * routes, top bar for public routes) lives in the route-group layouts
 * under ``(authed)/layout.tsx`` and ``(public)/layout.tsx``.
 */
import type { ReactNode } from "react";

import { AppProviders } from "@/components/AppProviders";

import "./globals.css";

export const metadata = {
  title: "Voyagent",
  description: "Agentic operating system for travel agencies.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-neutral-50 font-sans text-neutral-900 antialiased dark:bg-neutral-950 dark:text-neutral-100">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
