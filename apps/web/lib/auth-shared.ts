/**
 * Edge/middleware-safe auth primitives.
 *
 * This module MUST NOT import `server-only` because Next.js middleware runs
 * in the Edge runtime and pulls these symbols at the very top of the request
 * pipeline. Anything that needs Node APIs lives in `./auth.ts`.
 */

export const ACCESS_COOKIE = "voyagent_at";
export const REFRESH_COOKIE = "voyagent_rt";

/**
 * Decode a JWT's `exp` claim (seconds since epoch) and return ms-since-epoch.
 *
 * No signature verification — we trust that the cookie was set by our own
 * server action after a successful API response, and that an attacker
 * forging a JWT only buys themselves a redirect to a real API call which
 * will reject the token with 401.
 *
 * Returns 0 for any unparseable / missing input so callers can treat the
 * "no token" and "broken token" cases identically.
 */
export function jwtExpMs(token: string): number {
  if (!token) return 0;
  const parts = token.split(".");
  if (parts.length < 2) return 0;
  try {
    // base64url -> base64
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    // atob is available in both Edge and Node 18+ runtimes.
    const json = typeof atob === "function"
      ? atob(padded)
      : Buffer.from(padded, "base64").toString("binary");
    const decoded: unknown = JSON.parse(json);
    if (
      typeof decoded === "object" &&
      decoded !== null &&
      "exp" in decoded &&
      typeof (decoded as { exp: unknown }).exp === "number"
    ) {
      return (decoded as { exp: number }).exp * 1000;
    }
    return 0;
  } catch {
    return 0;
  }
}
