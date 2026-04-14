import { VoyagentClient } from "@voyagent/sdk";

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
 * Singleton `VoyagentClient`. The desktop shell has exactly one signed-in
 * user at a time, so a module-level instance is fine.
 *
 * TODO(auth): swap the no-auth client for one wired to Clerk's desktop
 * session token once the auth agent's work lands. The `authToken` option
 * accepts an async getter, which is exactly what Clerk will expose.
 */
export const voyagentClient = new VoyagentClient({ baseUrl: apiUrl });
