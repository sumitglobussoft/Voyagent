/**
 * Bridge between the desktop web layer and the Tauri Rust core.
 *
 * v0 (this file today): a thin wrapper over Tauri's `invoke()` that calls
 * the `local_driver_invoke` command registered in `src-tauri/src/main.rs`.
 * The Rust side currently returns a "not_wired_yet" stub for every call.
 *
 * v1 (future): this is the seam through which local drivers — Tally
 * ODBC, GDS terminals, smart-card readers, thermal printers — are called.
 * The cloud runtime already has a driver protocol; when a tool call
 * dispatches to a "local" driver, the runtime will send the invocation
 * down via SSE and the desktop shell will route it through this bridge
 * instead of making a remote HTTP call. Tally integration is the first
 * consumer — Tally XML-over-HTTP will live inside the Tauri sidecar and
 * be addressed as `driver = "tally"`.
 *
 * Keep this module free of React / DOM imports; it must be consumable
 * from workers or background contexts too.
 */

/**
 * Shape of every driver response. Concrete drivers will return richer
 * payloads; v0 Rust stub returns `{ status: "not_wired_yet", ... }`.
 */
export interface LocalDriverResponse {
  status: string;
  [key: string]: unknown;
}

export async function invokeLocalDriver(
  driver: string,
  method: string,
  args: Record<string, unknown>,
): Promise<LocalDriverResponse> {
  // Import lazily so the web build doesn't pull Tauri's runtime into
  // non-Tauri test environments (e.g., Vitest node jsdom).
  const { invoke } = await import("@tauri-apps/api/core");
  const result = await invoke<LocalDriverResponse>("local_driver_invoke", {
    driver,
    method,
    args,
  });
  return result;
}
