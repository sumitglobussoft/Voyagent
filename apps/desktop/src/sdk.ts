import { useMemo } from "react";

import { VoyagentClient } from "@voyagent/sdk";

import { useAuth } from "./auth/AuthProvider.js";

/**
 * Pull configuration off `import.meta.env` (Vite inlines these at build time).
 * We fall back to sensible dev defaults so the shell boots without an .env
 * file, but production builds should always inject explicit values.
 */
function readEnv(key: string, fallback: string): string {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  if (typeof raw === "string" && raw.length > 0) return raw;
  return fallback;
}

export const apiUrl = readEnv("VITE_VOYAGENT_API_URL", "http://localhost:8000");
export const tenantId = readEnv("VITE_VOYAGENT_TENANT_ID", "dev-tenant");
export const actorId = readEnv("VITE_VOYAGENT_ACTOR_ID", "dev-user");

/**
 * Build a `VoyagentClient` wired to the current Clerk session.
 *
 * This must run inside a component that sits under `<AuthProvider>`. The
 * `authToken` option accepts an async getter so the SDK reads a fresh
 * session JWT on every API call — same contract the web app uses.
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
              "Voyagent desktop: no Clerk session token available — user is signed out.",
            );
          }
          return token;
        },
      }),
    [getToken],
  );
}
