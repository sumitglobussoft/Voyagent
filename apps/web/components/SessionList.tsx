/**
 * Server component that fetches the most recent chat sessions for the
 * current tenant and renders them as a list of links for the sidebar.
 *
 * Title fallback ladder:
 *   1. ``session.title`` if the API provides it (auto-title work is
 *      coming from the parallel chat-component agent).
 *   2. ``"Conversation <short-id>"`` otherwise.
 *
 * Empty / failure state is a single muted line. We deliberately don't
 * surface HTTP errors here — the sidebar must never look broken just
 * because the list endpoint is briefly down.
 *
 * Active-session highlighting lives inside the small client component
 * ``SessionListItem`` — it needs ``usePathname`` + ``useSearchParams``
 * to match against the current URL.
 */
import type { ReactElement } from "react";

import { listChatSessions, type ChatSessionListItem } from "@/lib/api";
import { formatRelative } from "@/lib/formatting";

import { SessionListItem } from "./SessionListItem";

const MAX_TITLE_CHARS = 30;

function fallbackTitle(session: ChatSessionListItem): string {
  if (session.title && session.title.trim().length > 0) {
    const t = session.title.trim();
    return t.length > MAX_TITLE_CHARS ? `${t.slice(0, MAX_TITLE_CHARS - 1)}…` : t;
  }
  const shortId = session.id.slice(0, 8);
  return `Conversation ${shortId}`;
}

export async function SessionList(): Promise<ReactElement> {
  const sessions = await listChatSessions(30);

  if (sessions.length === 0) {
    return (
      <div
        style={{
          padding: "8px 12px",
          fontSize: 13,
          color: "#71717a",
          fontStyle: "italic",
        }}
      >
        No conversations yet.
      </div>
    );
  }

  return (
    <ul
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: 2,
      }}
    >
      {sessions.map((s) => {
        const title = fallbackTitle(s);
        const ts = s.updated_at ?? s.created_at ?? null;
        const relative = ts ? formatRelative(ts) : null;
        return (
          <SessionListItem
            key={s.id}
            id={s.id}
            title={title}
            relative={relative}
          />
        );
      })}
    </ul>
  );
}

export default SessionList;
