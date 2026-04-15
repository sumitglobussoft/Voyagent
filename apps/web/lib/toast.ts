/**
 * Server-side helper for queueing a toast from a Server Action.
 *
 * Server Actions cannot call React hooks, so to surface a success /
 * error message after a mutation we write a short-lived cookie that the
 * client ToastProvider drains on mount (see `ToastProvider.drainCookie`).
 *
 * Example:
 * ```ts
 * "use server";
 * import { queueServerToast } from "@/lib/toast";
 *
 * export async function saveProfile() {
 *   // ...do work...
 *   await queueServerToast("success", "Profile saved");
 * }
 * ```
 */
import { cookies } from "next/headers";

export type ServerToastKind = "success" | "error" | "info";

const COOKIE_NAME = "voyagent_toast";

export async function queueServerToast(
  kind: ServerToastKind,
  message: string,
): Promise<void> {
  const jar = await cookies();
  jar.set(COOKIE_NAME, JSON.stringify({ kind, message }), {
    path: "/",
    // Short-lived — just long enough to survive the redirect after the
    // action. The client clears it immediately on drain.
    maxAge: 30,
    httpOnly: false,
    sameSite: "lax",
  });
}
