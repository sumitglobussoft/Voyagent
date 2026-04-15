"use client";

/**
 * Minimal client component: one row in the sidebar's recent-sessions
 * list. Needed on the client ONLY to read the URL so the active
 * session can be highlighted.
 */
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactElement } from "react";

export interface SessionListItemProps {
  id: string;
  title: string;
  relative: string | null;
}

export function SessionListItem({
  id,
  title,
  relative,
}: SessionListItemProps): ReactElement {
  const pathname = usePathname();
  const params = useSearchParams();
  // `usePathname` returns the un-basePath'd path (e.g. "/chat").
  const isChat = pathname === "/chat" || pathname?.startsWith("/chat/");
  const activeSessionId = params?.get("session_id") ?? null;
  const isActive = isChat && activeSessionId === id;

  const href = `/chat?session_id=${encodeURIComponent(id)}`;

  return (
    <li>
      <Link
        href={href}
        style={{
          display: "block",
          padding: "6px 10px",
          borderRadius: 6,
          textDecoration: "none",
          color: "#18181b",
          background: isActive ? "#e4e4e7" : "transparent",
          fontSize: 13,
          lineHeight: 1.3,
        }}
      >
        <div
          style={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontWeight: isActive ? 600 : 400,
          }}
        >
          {title}
        </div>
        {relative ? (
          <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>
            {relative}
          </div>
        ) : null}
      </Link>
    </li>
  );
}
