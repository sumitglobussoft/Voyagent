import type { ReactNode } from "react";

import { Footer } from "./Footer";
import { TopNav } from "./TopNav";

/**
 * Top-level chrome for every marketing page.
 *
 * Renders the nav on top, a `<main id="main">` landmark that the skip-link
 * target resolves to, and a footer at the bottom. Pages receive a minimal
 * wrapper — they own their own section structure.
 */
export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <TopNav />
      <main id="main" className="flex-1">
        {children}
      </main>
      <Footer />
    </div>
  );
}
