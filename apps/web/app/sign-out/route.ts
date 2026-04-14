/**
 * Sign-out endpoint.
 *
 * POST: server-side call to /api/auth/sign-out, clears cookies, then
 * 303-redirects to "/" (the marketing root). 303 forces the browser to
 * follow with a GET regardless of the originating method.
 */
import { NextResponse, type NextRequest } from "next/server";
import { cookies } from "next/headers";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  clearSessionCookies,
  signOut,
} from "@/lib/auth";

export async function POST(req: NextRequest) {
  const jar = cookies();
  const at = jar.get(ACCESS_COOKIE)?.value ?? null;
  const rt = jar.get(REFRESH_COOKIE)?.value ?? null;

  await signOut(at, rt);
  clearSessionCookies();

  return NextResponse.redirect(new URL("/", req.url), { status: 303 });
}
