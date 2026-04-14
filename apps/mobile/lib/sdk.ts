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
 * Mobile-side Voyagent client. Uses React Native's global `fetch`. Auth
 * will be wired in later (Clerk Expo module) — the `authToken` option on
 * `VoyagentClient` accepts an async getter for that.
 */
export function makeVoyagentClient(): VoyagentClient {
  return new VoyagentClient({ baseUrl: apiUrl });
}
