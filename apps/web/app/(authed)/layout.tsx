/**
 * Authenticated (``/app/*``) route-group layout.
 *
 * Wraps every page under ``app/(authed)`` with a persistent left
 * sidebar (``AppSidebar``) and a flexible main content column.
 *
 * On viewports <768px the sidebar is swapped for a top-bar hamburger
 * (``MobileHeader``) that opens a slide-in drawer rendering the same
 * sidebar content. Responsive visibility is handled entirely via CSS
 * helpers in ``globals.css`` (``.voyagent-sidebar`` /
 * ``.voyagent-mobile-only``) so neither surface regresses the other.
 *
 * The middleware already redirects unauthenticated traffic to the
 * sign-in page, but we defend-in-depth here by calling
 * ``getCurrentUser()`` and redirecting if it comes back null — this
 * also hands the user object to the sidebar so the server component
 * can render the user card without a second round-trip.
 */
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/AppSidebar";
import { MobileHeader } from "@/components/MobileHeader";
import { getCurrentUser } from "@/lib/auth";

export default async function AuthedLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) {
    // Matches the middleware gate — signed-out users never see the
    // sidebar. ``next`` isn't set here because this layout has no
    // access to the requested path (Next 15 doesn't expose it to
    // server layouts); the middleware handles the ``next`` round-trip
    // on the next request cycle.
    redirect("/sign-in");
  }

  return (
    <div style={{ display: "flex", minHeight: "100dvh" }}>
      <AppSidebar user={user} />
      {/* The individual pages render their own <main> element, so this
          wrapper is a plain <div> to avoid nested <main> landmarks. */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          background: "#fafafa",
        }}
      >
        <MobileHeader user={user} />
        {children}
      </div>
    </div>
  );
}
