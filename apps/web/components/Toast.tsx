"use client";

/**
 * Individual toast row. Pure presentational — the parent
 * ToastProvider owns timers and dismiss logic.
 */
import type { ReactElement } from "react";

import { X } from "@voyagent/icons";

export type ToastKind = "success" | "error" | "info";

export type ToastShape = {
  id: string;
  kind: ToastKind;
  message: string;
};

export function Toast({
  toast,
  onDismiss,
}: {
  toast: ToastShape;
  onDismiss: (id: string) => void;
}): ReactElement {
  return (
    <div
      className="voyagent-toast"
      data-kind={toast.kind}
      data-testid="toast"
      role={toast.kind === "error" ? "alert" : "status"}
      aria-live={toast.kind === "error" ? "assertive" : "polite"}
    >
      <span style={{ flex: 1, minWidth: 0 }}>{toast.message}</span>
      <button
        type="button"
        className="voyagent-toast-dismiss"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export default Toast;
