/**
 * Typed wrapper over the Rust-side token store commands.
 *
 * The three Tauri commands (`auth_store_token`, `auth_load_token`,
 * `auth_clear_token`) are defined in `src-tauri/src/commands/auth.rs`.
 * This module is the single entrypoint — no other TS file should call
 * `invoke()` with those command names, so we can grep the codebase for
 * token access.
 *
 * NEVER log token values. `get()` returns the string so callers can
 * hand it straight to the Clerk SDK; do not `console.log` the result.
 */
import { invoke } from "@tauri-apps/api/core";

interface StoredTokenBlob {
  token: string;
  captured_at_ms: number;
}

export interface StoredToken {
  token: string;
  capturedAt: Date;
}

export const tokenStore = {
  async get(): Promise<StoredToken | null> {
    const blob = await invoke<StoredTokenBlob | null>("auth_load_token");
    if (blob === null) return null;
    return {
      token: blob.token,
      capturedAt: new Date(blob.captured_at_ms),
    };
  },

  async set(token: string): Promise<void> {
    await invoke<void>("auth_store_token", { token });
  },

  async clear(): Promise<void> {
    await invoke<void>("auth_clear_token");
  },
};
