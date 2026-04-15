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

  // Next 15 with basePath="/app" strips the basePath from pathname inside
  // middleware. So `/app/enquiries` shows up here as `/enquiries`, and
  // `/app/sign-in` as `/sign-in`. Normalize either form. Use an EXACT
  // prefix check (BASE_PATH or BASE_PATH + "/") so `/approvals` doesn't
  // misfire on the bare `/app` substring (`/approvals`.startsWith(`/app`)
  // is true and would slice to "rovals" — silent bug).
  const hasBasePath =
    pathname === BASE_PATH || pathname.startsWith(BASE_PATH + "/");
  const stripped = hasBasePath
    ? pathname.slice(BASE_PATH.length) || "/"
    : pathname;

  // Public sub-routes inside the gated app — let through.
  const publicPrefixes = [
    "/sign-in",
    "/sign-up",
    "/forgot-password",
    "/reset-password",
    "/accept-invite",
  ];
  if (
    publicPrefixes.some(
      (p) => stripped === p || stripped.startsWith(p + "/"),
    )
  ) {
    return NextResponse.next();
  }

  const at = req.cookies.get(ACCESS_COOKIE)?.value;
  const valid = at && jwtExpMs(at) > Date.now();
  if (valid) return NextResponse.next();

  const nextPath = safeNextPath(stripped === "/" ? "/chat" : stripped);

  // Build the absolute redirect URL from the inbound public host headers.
  // Using `req.url` or `req.nextUrl.origin` leaks the upstream
  // `http://127.0.0.1:3011` because we run `next start -H 127.0.0.1`
  // behind nginx. The host nginx sets X-Forwarded-Host + X-Forwarded-Proto.
  const proto =
    req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  const base = host ? `${proto}://${host}` : req.nextUrl.origin;
  const target = new URL("/app/sign-in", base);
  target.searchParams.set("next", nextPath);
  return NextResponse.redirect(target);
}

// Match every path inside the basePath (Next prepends `/app` automatically).
// Excluding `_next` static assets so we don't gate JS/CSS chunks.
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
