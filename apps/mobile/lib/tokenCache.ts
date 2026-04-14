/**
 * Secure-store-backed token cache for `@clerk/clerk-expo`.
 *
 * Clerk's Expo SDK expects a `tokenCache` object with `getToken` /
 * `saveToken` / `clearToken`. We back it with `expo-secure-store` so
 * the session JWT lives inside the iOS Keychain / Android Keystore
 * rather than AsyncStorage. Logs are neutral markers — never print
 * token values.
 */
import * as SecureStore from "expo-secure-store";

import type { TokenCache } from "@clerk/clerk-expo/dist/cache";

export const tokenCache: TokenCache = {
  async getToken(key: string): Promise<string | null> {
    try {
      const value = await SecureStore.getItemAsync(key);
      return value;
    } catch {
      return null;
    }
  },
  async saveToken(key: string, value: string): Promise<void> {
    try {
      await SecureStore.setItemAsync(key, value);
    } catch {
      // Swallow — Clerk retries on the next refresh anyway.
    }
  },
};
