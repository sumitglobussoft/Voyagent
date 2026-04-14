import type { ReactNode } from "react";

import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
} from "@clerk/nextjs";

export const metadata = {
  title: "Voyagent",
  description: "Agentic operating system for travel agencies.",
};

// Every page on the authenticated app is tenant-scoped and calls Clerk at
// request time. Forcing dynamic rendering avoids prerendering during
// `next build`, which otherwise fails when the Clerk publishable key is
// not yet injected in the build environment.
export const dynamic = "force-dynamic";

/**
 * Root layout.
 *
 * Wraps the entire app in `<ClerkProvider>` so client components can call
 * `useAuth()` / `useUser()`. The small header lane renders a user avatar
 * (signed-in) or a sign-in button (signed-out) — the minimum affordance
 * a tenant-aware workspace needs at the top-right of every page.
 *
 * Actual route protection happens in `middleware.ts`; this header is
 * purely visual.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          <header
            style={{
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              padding: "12px 24px",
              borderBottom: "1px solid #eee",
              fontFamily: "system-ui, sans-serif",
            }}
          >
            <SignedIn>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
            <SignedOut>
              <SignInButton mode="modal" />
            </SignedOut>
          </header>
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
