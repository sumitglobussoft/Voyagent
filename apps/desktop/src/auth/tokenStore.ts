/**
 * Typed wrapper over the Rust-side secure token store commands.
 *
 * The three Tauri commands (`voyagent_store_session`, `voyagent_load_session`,
 * `voyagent_clear_session`) are defined in `src-tauri/src/commands/auth.rs`.
 * This module is the single entrypoint — no other TS file should call
 * `invoke()` with those command names, so we can grep the codebase for
 * token access.
 *
 * NEVER log token values.
 */
import { invoke } from "@tauri-apps/api/core";

import type { DesktopUser } from "./VoyagentAuthClient.js";

interface StoredSessionBlob {
  access_token: string;
  refresh_token: string;
  user: DesktopUser | null;
}

export interface StoredSession {
  accessToken: string;
  refreshToken: string;
  user: DesktopUser | null;
}

export const tokenStore = {
  async get(): Promise<StoredSession | null> {
    const blob = await invoke<StoredSessionBlob | null>("voyagent_load_session");
    if (blob === null) return null;
    return {
      accessToken: blob.access_token,
      refreshToken: blob.refresh_token,
      user: blob.user,
    };
  },

  async set(session: StoredSession): Promise<void> {
    await invoke<void>("voyagent_store_session", {
      session: {
        access_token: session.accessToken,
        refresh_token: session.refreshToken,
        user: session.user,
      },
    });
  },

  async clear(): Promise<void> {
    await invoke<void>("voyagent_clear_session");
  },
};
