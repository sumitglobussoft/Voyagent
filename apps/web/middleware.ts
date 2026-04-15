/**
 * Voyagent web app middleware.
 *
 * Gates `/app/*` behind a presence-and-expiry check on the access-token
 * cookie. We deliberately do NOT verify the JWT signature here — that's
 * the API's job. The middleware just needs to be fast enough to run on
 * every authenticated request without hammering the backend.
 *
 * Public sub-routes (`/app/sign-in`, `/app/sign-up`) are allowed through
 * so the unauth flow can render. Anything else under `/app/*` without a
 * non-expired access cookie is redirected to sign-in with `?next=` set
 * to the original path (with the `/app` basePath stripped, because the
 * sign-in action hands the value straight to `redirect()` which
 * re-prepends the basePath).
 *
 * Implementation note: we build the redirect URL with the standard
 * `URL` constructor against `req.url` rather than mutating
 * `req.nextUrl.clone()`. In Next 15 setting `.pathname` on a `NextURL`
 * interacts with the configured basePath in ways that have silently
 * swallowed the `searchParams.set("next", ...)` call in past builds —
 * plain URL has no such magic so what we build is what ships.
 */
import { NextResponse, type NextRequest } from "next/server";

import { ACCESS_COOKIE, jwtExpMs } from "./lib/auth-shared";
import { safeNextPath } from "./lib/next-url";

const BASE_PATH = "/app";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const publicPrefixes = ["/app/sign-in", "/app/sign-up"];
  if (publicPrefixes.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  if (!pathname.startsWith("/app")) {
    return NextResponse.next();
  }

  const at = req.cookies.get(ACCESS_COOKIE)?.value;
  const valid = at && jwtExpMs(at) > Date.now();

  if (!valid) {
    // Strip the /app basePath from `next` so the sign-in action can
    // pass it directly to redirect() — Next prepends basePath again.
    const stripped = pathname.startsWith(BASE_PATH)
      ? pathname.slice(BASE_PATH.length) || "/chat"
      : pathname;
    const nextPath = safeNextPath(stripped);

    // Build the absolute redirect URL from the inbound public Host +
    // X-Forwarded-Proto headers — never `req.url`, which carries the
    // upstream `http://127.0.0.1:3011` when running behind nginx +
    // `next start -H 127.0.0.1`. Falling through to req.nextUrl.origin
    // would have the same leak. The base is reconstructed from headers.
    const proto =
      req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
    const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
    if (!host) {
      // Should never happen — every HTTP request carries a Host header. If
      // it does, fall back to the relative form (browsers handle relative
      // Location headers fine even though the spec recommends absolute).
      return NextResponse.redirect(
        `/app/sign-in?next=${encodeURIComponent(nextPath)}` as unknown as URL,
      );
    }
    const target = new URL(`${proto}://${host}/app/sign-in`);
    target.searchParams.set("next", nextPath);
    return NextResponse.redirect(target);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*"],
};
