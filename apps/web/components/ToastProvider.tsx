"use client";

/**
 * ToastProvider — tiny in-memory toast queue + portal container.
 *
 * ## Why a cookie bridge?
 *
 * Server Actions run on the server and cannot dispatch to client React
 * state. The standard Next 15 trick for this is to have the server
 * action set a short-lived cookie ("voyagent_toast") that the next
 * client render drains. On mount, this provider reads the cookie, pops
 * any pending payload onto the in-memory queue, and then clears the
 * cookie so refreshing doesn't replay the same toast.
 *
 * ## API
 *
 * ```tsx
 * const toast = useToast();
 * toast.success("Saved"); toast.error("Boom"); toast.info("Heads up");
 * ```
 *
 * Toasts auto-dismiss after 4s and support manual dismissal via the X.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Toast, type ToastKind, type ToastShape } from "./Toast";

type ToastAPI = {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
};

const ToastContext = createContext<ToastAPI | null>(null);

const AUTO_DISMISS_MS = 4000;
const COOKIE_NAME = "voyagent_toast";

function drainCookie(): ToastShape | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${COOKIE_NAME}=`));
  if (!match) return null;
  const raw = decodeURIComponent(match.slice(COOKIE_NAME.length + 1));
  // Clear immediately so a reload doesn't replay it.
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`;
  try {
    const parsed = JSON.parse(raw) as { kind?: ToastKind; message?: string };
    if (!parsed.message) return null;
    const kind: ToastKind =
      parsed.kind === "success" || parsed.kind === "error" || parsed.kind === "info"
        ? parsed.kind
        : "info";
    return {
      id: `server-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      kind,
      message: parsed.message,
    };
  } catch {
    return null;
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastShape[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, kind, message }]);
      const handle = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timers.current.set(id, handle);
    },
    [dismiss],
  );

  // Drain server-action cookie on mount.
  useEffect(() => {
    const pending = drainCookie();
    if (pending) {
      setToasts((prev) => [...prev, pending]);
      const handle = setTimeout(() => dismiss(pending.id), AUTO_DISMISS_MS);
      timers.current.set(pending.id, handle);
    }
  }, [dismiss]);

  // Cleanup any outstanding timers on unmount.
  useEffect(() => {
    const current = timers.current;
    return () => {
      for (const handle of current.values()) clearTimeout(handle);
      current.clear();
    };
  }, []);

  const api = useMemo<ToastAPI>(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="voyagent-toast-container" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <Toast key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastAPI {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}
