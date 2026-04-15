/**
 * Persistent left sidebar for the authenticated web surface.
 *
 * ChatGPT-style layout:
 *   - "New chat" pill at the top (links to ``/chat?new=1`` — the chat
 *     host is expected to interpret ``?new=1`` as a fresh-session
 *     request; if it doesn't today, the worst case is the chat page
 *     renders its standard fresh state which is still correct).
 *   - "Recent" list of chat sessions (server-fetched).
 *   - "Workspace" nav (Chat / Enquiries / Approvals / Audit).
 *     Reports is intentionally skipped — no page exists yet, only
 *     the API surface.
 *   - User card at the bottom with avatar, name, tenant, role badge
 *     and sign-out form.
 *
 * Styling uses the existing inline-style approach so we don't have to
 * introduce Tailwind / Tamagui / CSS modules to this app (which uses
 * none today). Right border + slightly off-white background
 * differentiate the sidebar from the ``#fafafa`` main content area.
 */
import Link from "next/link";
import { Suspense, type ReactElement } from "react";

import { Check, FileText, Receipt, Send } from "@voyagent/icons";

import type { PublicUser } from "@/lib/auth";

import { NavLink } from "./NavLink";
import { SessionList } from "./SessionList";
import { UserCard } from "./UserCard";

export const SIDEBAR_WIDTH = 256;

export function AppSidebar({ user }: { user: PublicUser }): ReactElement {
  return (
    <aside
      className="voyagent-sidebar"
      style={{
        width: SIDEBAR_WIDTH,
        flex: `0 0 ${SIDEBAR_WIDTH}px`,
        height: "100dvh",
        position: "sticky",
        top: 0,
        background: "#f4f4f5",
        borderRight: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
        boxSizing: "border-box",
        overflow: "hidden",
      }}
    >
      {/* Top — wordmark + new chat */}
      <div style={{ padding: "14px 12px 8px 12px" }}>
        <a
          href="/"
          style={{
            display: "block",
            fontWeight: 700,
            fontSize: 18,
            color: "#111",
            textDecoration: "none",
            padding: "2px 6px 10px 6px",
          }}
        >
          Voyagent
        </a>
        <Link
          href="/chat?new=1"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            width: "100%",
            padding: "10px 12px",
            borderRadius: 999,
            background: "#18181b",
            color: "#fafafa",
            textDecoration: "none",
            fontSize: 14,
            fontWeight: 500,
            boxSizing: "border-box",
          }}
        >
          <span
            aria-hidden
            style={{
              fontSize: 16,
              lineHeight: 1,
              fontWeight: 400,
              marginTop: -1,
            }}
          >
            +
          </span>
          New chat
        </Link>
      </div>

      {/* Middle — recent sessions */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          padding: "8px 8px 8px 8px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: "#71717a",
            padding: "4px 6px",
            fontWeight: 600,
          }}
        >
          Recent
        </div>
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            paddingRight: 2,
          }}
        >
          <Suspense
            fallback={
              <div
                style={{
                  padding: "8px 12px",
                  fontSize: 13,
                  color: "#a1a1aa",
                }}
              >
                Loading…
              </div>
            }
          >
            {/* Server component — fetches on every render */}
            <SessionList />
          </Suspense>
        </div>
      </div>

      {/* Workspace nav */}
      <div
        style={{
          borderTop: "1px solid #e5e7eb",
          padding: "10px 8px",
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        <div
          style={{
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: "#71717a",
            padding: "4px 6px",
            fontWeight: 600,
          }}
        >
          Workspace
        </div>
        <NavLink href="/chat" label="Chat" icon={<Send size={16} />} />
        <NavLink
          href="/enquiries"
          label="Enquiries"
          icon={<FileText size={16} />}
        />
        <NavLink
          href="/approvals"
          label="Approvals"
          icon={<Check size={16} />}
        />
        <NavLink href="/audit" label="Audit" icon={<Receipt size={16} />} />
      </div>

      {/* Bottom — user */}
      <UserCard user={user} />
    </aside>
  );
}

export default AppSidebar;
