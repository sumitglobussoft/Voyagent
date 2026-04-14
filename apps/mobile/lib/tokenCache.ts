/**
 * SecureStore-backed token store for Voyagent's cookie-free mobile auth.
 *
 * React Native can't share HttpOnly cookies with the web app, so we persist
 * the access token, refresh token, and the cached user payload in
 * expo-secure-store (iOS Keychain / Android Keystore). Keys are namespaced
 * under `voyagent.*` so a future multi-account world can list them cleanly.
 */
import * as SecureStore from "expo-secure-store";

import type { PublicUser } from "./auth-types";

const ACCESS_KEY = "voyagent.access_token";
const REFRESH_KEY = "voyagent.refresh_token";
const USER_KEY = "voyagent.user";

async function getItem(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function setItem(key: string, value: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(key, value);
  } catch {
    // Swallow — next write retries.
  }
}

async function delItem(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key);
  } catch {
    // Swallow.
  }
}

export const TokenStore = {
  async getAccessToken(): Promise<string | null> {
    return getItem(ACCESS_KEY);
  },
  async setAccessToken(value: string): Promise<void> {
    await setItem(ACCESS_KEY, value);
  },
  async getRefreshToken(): Promise<string | null> {
    return getItem(REFRESH_KEY);
  },
  async setRefreshToken(value: string): Promise<void> {
    await setItem(REFRESH_KEY, value);
  },
  async getUser(): Promise<PublicUser | null> {
    const raw = await getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as PublicUser;
    } catch {
      return null;
    }
  },
  async setUser(user: PublicUser): Promise<void> {
    await setItem(USER_KEY, JSON.stringify(user));
  },
  async clear(): Promise<void> {
    await Promise.all([
      delItem(ACCESS_KEY),
      delItem(REFRESH_KEY),
      delItem(USER_KEY),
    ]);
  },
};
