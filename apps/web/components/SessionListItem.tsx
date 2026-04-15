"use client";

/**
 * Minimal client component: one row in the sidebar's recent-sessions
 * list. Needed on the client to read the URL so the active session
 * can be highlighted AND to provide hover affordances for rename +
 * delete.
 *
 * Rename is an inline input that replaces the title on click and
 * commits on Enter / blur.
 * Delete round-trips through ``?confirm_delete=<id>`` so users can
 * see a confirmation prompt on the chat page before the destructive
 * server action fires. This matches the enquiries cancel pattern.
 */
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type ReactElement, useTransition } from "react";

import {
  deleteChatSession,
  renameChatSession,
} from "../app/(authed)/chat/actions";

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
  const isChat = pathname === "/chat" || pathname?.startsWith("/chat/");
  const activeSessionId = params?.get("session_id") ?? null;
  const isActive = isChat && activeSessionId === id;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [hovered, setHovered] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const href = `/chat?session_id=${encodeURIComponent(id)}`;
  const confirmHref = `/chat?session_id=${encodeURIComponent(id)}&confirm_delete=1`;

  function onRenameSubmit(): void {
    const next = draft.trim();
    if (!next || next === title) {
      setEditing(false);
      setDraft(title);
      return;
    }
    startTransition(async () => {
      const result = await renameChatSession(id, next);
      if (!result.ok) {
        setError(result.error ?? "rename_failed");
        setDraft(title);
      } else {
        setError(null);
      }
      setEditing(false);
    });
  }

  function onDelete(): void {
    startTransition(async () => {
      const result = await deleteChatSession(id);
      if (!result.ok) {
        setError(result.error ?? "delete_failed");
      }
    });
  }

  // If the URL has ``confirm_delete=1`` for THIS row we also render
  // an inline confirm / cancel pair.
  const askingDelete =
    isActive && params?.get("confirm_delete") === "1";

  return (
    <li
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ position: "relative" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "6px 10px",
          borderRadius: 6,
          background: isActive ? "#e4e4e7" : "transparent",
          fontSize: 13,
          lineHeight: 1.3,
          gap: 6,
        }}
      >
        {editing ? (
          <input
            autoFocus
            value={draft}
            maxLength={200}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={onRenameSubmit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onRenameSubmit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setEditing(false);
                setDraft(title);
              }
            }}
            disabled={pending}
            style={{
              flex: 1,
              fontSize: 13,
              padding: "2px 4px",
              border: "1px solid #d4d4d8",
              borderRadius: 4,
              background: "#fff",
            }}
          />
        ) : (
          <Link
            href={href}
            style={{
              flex: 1,
              textDecoration: "none",
              color: "#18181b",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontWeight: isActive ? 600 : 400,
            }}
          >
            {title}
          </Link>
        )}

        {!editing && (hovered || askingDelete) && !pending && (
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <button
              type="button"
              aria-label="Rename session"
              onClick={(e) => {
                e.preventDefault();
                setDraft(title);
                setEditing(true);
              }}
              style={{
                fontSize: 11,
                padding: "2px 6px",
                border: "1px solid #d4d4d8",
                borderRadius: 4,
                background: "#fff",
                cursor: "pointer",
              }}
            >
              Rename
            </button>
            {askingDelete ? (
              <>
                <button
                  type="button"
                  aria-label="Confirm delete"
                  onClick={(e) => {
                    e.preventDefault();
                    onDelete();
                  }}
                  style={{
                    fontSize: 11,
                    padding: "2px 6px",
                    border: "1px solid #fca5a5",
                    borderRadius: 4,
                    background: "#fee2e2",
                    color: "#991b1b",
                    cursor: "pointer",
                  }}
                >
                  Confirm
                </button>
                <Link
                  href={href}
                  aria-label="Cancel delete"
                  style={{
                    fontSize: 11,
                    padding: "2px 6px",
                    border: "1px solid #d4d4d8",
                    borderRadius: 4,
                    background: "#fff",
                    color: "#18181b",
                    textDecoration: "none",
                  }}
                >
                  Cancel
                </Link>
              </>
            ) : (
              <Link
                href={confirmHref}
                aria-label="Delete session"
                style={{
                  fontSize: 11,
                  padding: "2px 6px",
                  border: "1px solid #fca5a5",
                  borderRadius: 4,
                  background: "#fff",
                  color: "#991b1b",
                  textDecoration: "none",
                }}
              >
                Delete
              </Link>
            )}
          </div>
        )}
      </div>
      {relative && !editing ? (
        <div
          style={{
            fontSize: 11,
            color: "#71717a",
            marginTop: 2,
            padding: "0 10px",
          }}
        >
          {relative}
        </div>
      ) : null}
      {error ? (
        <div
          role="alert"
          style={{
            fontSize: 11,
            color: "#991b1b",
            padding: "2px 10px",
          }}
        >
          {error}
        </div>
      ) : null}
    </li>
  );
}
