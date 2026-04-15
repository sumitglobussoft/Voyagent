/**
 * Authenticated (``/app/*``) route-group layout.
 *
 * Wraps every page under ``app/(authed)`` with a persistent left
 * sidebar (``AppSidebar``) and a flexible main content column.
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
      {/* Hide the sidebar on narrow viewports (<768px). The 256px
          sidebar overlaps page content on a ~400px mobile viewport and
          blocks clicks. Proper mobile drawer is a follow-up; for now
          mobile users see the page content full-width without sidebar
          nav. The `voyagent-sidebar` class + media query below
          accomplishes this without introducing a CSS framework. */}
      <style>{`
        @media (max-width: 767px) {
          .voyagent-sidebar { display: none !important; }
        }
      `}</style>
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
        {children}
      </div>
    </div>
  );
}
