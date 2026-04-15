"use server";

/**
 * Server actions for chat session CRUD.
 *
 * These power the rename + delete hover affordances on the sidebar's
 * SessionListItem. They proxy the authenticated Bearer token through
 * the server-only ``lib/api`` helper and revalidate the sidebar list
 * on success so the UI updates without a full page reload.
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { apiDelete, apiErrorCode, apiPatch } from "../../../lib/api";

export type ChatSessionActionResult = {
  ok: boolean;
  error: string | null;
};

/**
 * Rename a chat session's title.
 *
 * Validation happens both here (trim + length) and on the server; the
 * server is the source of truth so we let it reject malformed bodies
 * and surface the ``detail`` string back to the caller.
 */
export async function renameChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionActionResult> {
  const trimmed = (title ?? "").trim();
  if (!trimmed) {
    return { ok: false, error: "title_empty" };
  }
  if (trimmed.length > 200) {
    return { ok: false, error: "title_too_long" };
  }

  const res = await apiPatch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    title: trimmed,
  });
  if (!res.ok) {
    return {
      ok: false,
      error: apiErrorCode(res.data) ?? `http_${res.status}`,
    };
  }
  revalidatePath("/chat");
  return { ok: true, error: null };
}

/**
 * Delete a chat session (cascades messages + approvals on the API side).
 *
 * Callers invoke this from a two-step confirmation flow (the hover
 * menu's Delete opens ``/chat?confirm_delete=<id>`` first; that page
 * re-submits to this action). Successful delete redirects to the
 * bare ``/chat`` route so no stale ``session_id`` lingers in the URL.
 */
export async function deleteChatSession(
  sessionId: string,
): Promise<ChatSessionActionResult> {
  const res = await apiDelete(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
  if (!res.ok && res.status !== 204) {
    return {
      ok: false,
      error: apiErrorCode(res.data) ?? `http_${res.status}`,
    };
  }
  revalidatePath("/chat");
  redirect("/chat");
}
