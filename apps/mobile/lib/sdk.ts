import { useMemo } from "react";

import { VoyagentClient } from "@voyagent/sdk";

import { VoyagentAuth } from "./auth";

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
 * Mobile-side Voyagent client. Every outgoing request asks VoyagentAuth
 * for a fresh access token; the store auto-refreshes when the JWT is
 * within 30s of expiry.
 */
export function useVoyagentClient(): VoyagentClient {
  return useMemo(
    () =>
      new VoyagentClient({
        baseUrl: apiUrl,
        authToken: async (): Promise<string> => {
          const token = await VoyagentAuth.getAccessToken();
          if (!token) {
            throw new Error(
              "Voyagent mobile: no access token available — user is signed out.",
            );
          }
          return token;
        },
      }),
    [],
  );
}

/**
 * Auth-less client — used only for the pre-auth smoke check.
 */
export function makeVoyagentClient(): VoyagentClient {
  return new VoyagentClient({ baseUrl: apiUrl });
}
