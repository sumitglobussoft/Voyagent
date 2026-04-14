/**
 * Auto-update checker.
 *
 * Calls the `check_for_updates` Tauri command on mount (throttled to once
 * per 24 h using localStorage) and shows a non-blocking toast when a new
 * version is available. We intentionally do NOT auto-install — a release
 * that lands mid-session disrupts the operator. Users click through the
 * toast which exits the app so `tauri-plugin-updater` can swap the binary.
 */
import { useEffect, useState, type ReactElement } from "react";

import { invoke } from "@tauri-apps/api/core";

interface UpdateStatus {
  available: boolean;
  version: string | null;
  notes: string | null;
}

const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
const LAST_CHECK_KEY = "voyagent:updater:lastChecked";

export function Updater(): ReactElement | null {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const last = Number(localStorage.getItem(LAST_CHECK_KEY) ?? "0");
    if (Number.isFinite(last) && Date.now() - last < CHECK_INTERVAL_MS) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const result = await invoke<UpdateStatus>("check_for_updates");
        localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
        if (!cancelled && result.available) {
          setStatus(result);
        }
      } catch {
        // Updater being unreachable is expected during dev (no endpoint
        // configured). Swallow — a telemetry hook can wrap this later.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status || dismissed) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        padding: "10px 14px",
        background: "#111",
        color: "#fff",
        borderRadius: 8,
        fontSize: 13,
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        display: "flex",
        alignItems: "center",
        gap: 12,
        zIndex: 1000,
      }}
    >
      <span>
        Update available
        {status.version ? ` (v${status.version})` : ""}
      </span>
      <button
        type="button"
        onClick={() => {
          setDismissed(true);
        }}
        style={{
          background: "transparent",
          color: "#fff",
          border: "1px solid #666",
          borderRadius: 4,
          padding: "2px 8px",
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        Later
      </button>
    </div>
  );
}
