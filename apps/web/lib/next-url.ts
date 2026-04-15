/**
 * Open-redirect safe `next` handling.
 *
 * The sign-in / sign-up flow ferries an original deep-link through a
 * `?next=` query param so users land where they were going after auth.
 * If we ever accept that value unchecked an attacker can turn sign-in
 * into a redirector: `/app/sign-in?next=//evil.com` -> sign in -> browser
 * follows `Location: //evil.com`.
 *
 * This validator admits only internal paths: a single leading slash,
 * no protocol-relative `//...`, no scheme (`javascript:`, `data:`,
 * `https://...`), no backslash (Windows path quirk). Anything else
 * falls back to the safe default.
 *
 * The `next` value is always passed WITHOUT the `/app` basePath —
 * Next.js re-prepends it when `redirect()` is called, so handing
 * `/app/...` back to `redirect()` would double-prefix.
 */
export const SAFE_NEXT_DEFAULT = "/chat";

export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return SAFE_NEXT_DEFAULT;
  const value = String(raw);

  // Must start with a single slash.
  if (!value.startsWith("/")) return SAFE_NEXT_DEFAULT;
  // Reject protocol-relative `//host/...` (browsers resolve to absolute).
  if (value.startsWith("//")) return SAFE_NEXT_DEFAULT;
  // Reject Windows-style separators masquerading as slashes.
  if (value.includes("\\")) return SAFE_NEXT_DEFAULT;
  // Reject schemes — colon before the first slash means scheme:path.
  // Any colon in a legitimate internal path is suspicious; reject.
  if (value.includes(":")) return SAFE_NEXT_DEFAULT;

  return value;
}
