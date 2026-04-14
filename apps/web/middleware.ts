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
 * to the original path.
 */
import { NextResponse, type NextRequest } from "next/server";

import { ACCESS_COOKIE, jwtExpMs } from "./lib/auth-shared";

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
    const url = req.nextUrl.clone();
    url.pathname = "/app/sign-in";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*"],
};
