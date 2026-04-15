"use client";

/**
 * Narrow-viewport top bar that owns the mobile navigation drawer.
 *
 * Rendered by the authed layout alongside ``<AppSidebar>``. CSS in
 * ``globals.css`` hides this header on viewports ≥768px and hides
 * ``<AppSidebar>`` on viewports <768px, so the two never appear at
 * the same time and neither regresses the other.
 *
 * Layout: hamburger button on the left, "Voyagent" wordmark next to
 * it. Clicking the hamburger opens the ``<MobileDrawer>`` which
 * contains the same ``SidebarContent`` the desktop sidebar uses.
 */
import { useState, type ReactElement, type ReactNode } from "react";

import { MobileDrawer } from "./MobileDrawer";

/**
 * Client component — owns the drawer's `isOpen` state only. The
 * sidebar content itself is passed in as `children` from the server
 * layout so we don't transitively import server-only modules through
 * a client boundary.
 */
export function MobileHeader({
  children,
}: {
  children: ReactNode;
}): ReactElement {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <header
        className="voyagent-mobile-header voyagent-mobile-only"
        role="banner"
      >
        <button
          type="button"
          className="voyagent-hamburger"
          aria-label="Open menu"
          aria-expanded={isOpen}
          aria-controls="voyagent-mobile-drawer"
          onClick={() => setIsOpen(true)}
        >
          {/* Three-bar hamburger drawn in pure CSS — no icon font. */}
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </button>
        <a href="/" className="voyagent-mobile-wordmark">
          Voyagent
        </a>
      </header>
      <div className="voyagent-mobile-only" id="voyagent-mobile-drawer">
        <MobileDrawer isOpen={isOpen} onClose={() => setIsOpen(false)}>
          {children}
        </MobileDrawer>
      </div>
    </>
  );
}

export default MobileHeader;
