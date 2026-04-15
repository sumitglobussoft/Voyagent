"use client";

/**
 * Slide-in navigation drawer for narrow viewports.
 *
 * Rendering responsibilities:
 *   - Backdrop (fixed, full-screen, dims underneath content) — fades
 *     in via opacity when ``isOpen`` flips. ``aria-hidden`` because
 *     it's decorative.
 *   - Panel (fixed, left-aligned, 280px wide) — slides in/out via a
 *     CSS ``transform: translateX`` transition. Holds the same
 *     ``SidebarContent`` the desktop sidebar uses.
 *
 * Accessibility:
 *   - Panel has ``role="dialog"`` ``aria-modal="true"`` with a label
 *     so screen readers announce it as a nav dialog.
 *   - Escape key dismisses while open.
 *   - TODO(v1): focus trap + return-focus-to-trigger + swipe-to-dismiss.
 *     v0 relies on Escape + backdrop-tap + nav-link-tap for dismissal.
 *
 * No animation library — plain CSS transitions on transform + opacity.
 */
import { useEffect, type ReactElement } from "react";

import type { PublicUser } from "@/lib/auth";

import { SidebarContent } from "./AppSidebar";

export interface MobileDrawerProps {
  user: PublicUser;
  isOpen: boolean;
  onClose: () => void;
}

export function MobileDrawer({
  user,
  isOpen,
  onClose,
}: MobileDrawerProps): ReactElement {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  // Lock body scroll while drawer is open so the page underneath
  // doesn't scroll when the user drags inside the drawer.
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen]);

  return (
    <>
      <div
        className="voyagent-drawer-backdrop"
        data-open={isOpen ? "true" : "false"}
        aria-hidden="true"
        onClick={onClose}
      />
      <aside
        className="voyagent-drawer-panel"
        data-open={isOpen ? "true" : "false"}
        role="dialog"
        aria-modal="true"
        aria-label="Primary navigation"
      >
        <SidebarContent user={user} onNavClick={onClose} />
      </aside>
    </>
  );
}

export default MobileDrawer;
