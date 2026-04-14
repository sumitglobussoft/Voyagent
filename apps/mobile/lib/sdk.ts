import { useMemo } from "react";

import { useAuth } from "@clerk/clerk-expo";
import { VoyagentClient } from "@voyagent/sdk";

/**
 * `process.env.EXPO_PUBLIC_*` is populated by Expo at build time from the
 * app's env files. We fall back to a sensible dev default so the app can
 * boot during local iteration without an `.env` present.
 */
function env(key: string, fallback: string): string {
  const value = process.env[key];
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

export const apiUrl = env(
  "EXPO_PUBLIC_VOYAGENT_API_URL",
  "http://localhost:8000",
);
export const tenantId = env("EXPO_PUBLIC_VOYAGENT_TENANT_ID", "dev-tenant");
export const actorId = env("EXPO_PUBLIC_VOYAGENT_ACTOR_ID", "dev-user");

/**
 * Mobile-side Voyagent client. Uses React Native's global `fetch`. The
 * client is wired to Clerk — every outgoing request asks `useAuth().getToken()`
 * for a fresh session JWT (Clerk refreshes internally).
 *
 * Must be called inside a component that sits under `<ClerkProvider>`.
 */
export function useVoyagentClient(): VoyagentClient {
  const { getToken } = useAuth();
  return useMemo(
    () =>
      new VoyagentClient({
        baseUrl: apiUrl,
        authToken: async (): Promise<string> => {
          const token = await getToken();
          if (!token) {
            throw new Error(
              "Voyagent mobile: no Clerk session token available — user is signed out.",
            );
          }
          return token;
        },
      }),
    [getToken],
  );
}

/**
 * Auth-less client — used only for the pre-auth smoke check. Prefer
 * `useVoyagentClient` for any surface that talks to protected endpoints.
 */
export function makeVoyagentClient(): VoyagentClient {
  return new VoyagentClient({ baseUrl: apiUrl });
}
