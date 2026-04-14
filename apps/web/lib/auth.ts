import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_COOKIE, REFRESH_COOKIE, jwtExpMs } from "./auth-shared";

export { ACCESS_COOKIE, REFRESH_COOKIE, jwtExpMs };

export type PublicUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tenant_id: string;
  tenant_name: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user?: PublicUser;
};

type ApiError = { error: string };

const REFRESH_LIFETIME_SECONDS = 60 * 60 * 24 * 30; // 30 days
const SKEW_MS = 30_000;

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

function isProd(): boolean {
  return process.env.NODE_ENV === "production";
}

async function postJson(
  path: string,
  body: unknown,
  headers: Record<string, string> = {},
): Promise<{ ok: boolean; status: number; data: unknown }> {
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...headers,
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    let data: unknown = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    console.error("voyagent.auth.postJson failed", { path, err });
    return { ok: false, status: 0, data: null };
  }
}

function extractDetail(data: unknown): string | null {
  if (
    typeof data === "object" &&
    data !== null &&
    "detail" in data &&
    typeof (data as { detail: unknown }).detail === "string"
  ) {
    return (data as { detail: string }).detail;
  }
  return null;
}

function asAuthResponse(data: unknown): AuthResponse | null {
  if (
    typeof data === "object" &&
    data !== null &&
    "access_token" in data &&
    "refresh_token" in data &&
    "expires_in" in data
  ) {
    const d = data as Record<string, unknown>;
    if (
      typeof d.access_token === "string" &&
      typeof d.refresh_token === "string" &&
      typeof d.expires_in === "number"
    ) {
      return {
        access_token: d.access_token,
        refresh_token: d.refresh_token,
        expires_in: d.expires_in,
        user: (d.user as PublicUser | undefined) ?? undefined,
      };
    }
  }
  return null;
}

function asPublicUser(data: unknown): PublicUser | null {
  if (
    typeof data === "object" &&
    data !== null &&
    "id" in data &&
    "email" in data &&
    "tenant_id" in data
  ) {
    return data as PublicUser;
  }
  return null;
}

export async function signUp(input: {
  email: string;
  password: string;
  full_name: string;
  agency_name: string;
}): Promise<AuthResponse | ApiError> {
  const res = await postJson("/api/auth/sign-up", input);
  if (res.ok) {
    const auth = asAuthResponse(res.data);
    if (auth) return auth;
    return { error: "invalid_response" };
  }
  return { error: extractDetail(res.data) ?? "request_failed" };
}

export async function signIn(input: {
  email: string;
  password: string;
}): Promise<AuthResponse | ApiError> {
  const res = await postJson("/api/auth/sign-in", input);
  if (res.ok) {
    const auth = asAuthResponse(res.data);
    if (auth) return auth;
    return { error: "invalid_response" };
  }
  return { error: extractDetail(res.data) ?? "request_failed" };
}

export async function refresh(refreshToken: string): Promise<AuthResponse | null> {
  const res = await postJson("/api/auth/refresh", { refresh_token: refreshToken });
  if (!res.ok) return null;
  return asAuthResponse(res.data);
}

export async function signOut(
  accessToken: string | null,
  refreshToken: string | null,
): Promise<void> {
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  await postJson("/api/auth/sign-out", { refresh_token: refreshToken }, headers);
}

export async function fetchMe(accessToken: string): Promise<PublicUser | null> {
  try {
    const res = await fetch(`${apiBase()}/api/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    return asPublicUser(data);
  } catch (err) {
    console.error("voyagent.auth.fetchMe failed", err);
    return null;
  }
}

export function setSessionCookies(
  access: string,
  refreshToken: string,
  expiresIn: number,
): void {
  const jar = cookies();
  const secure = isProd();
  jar.set(ACCESS_COOKIE, access, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: expiresIn,
  });
  jar.set(REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_LIFETIME_SECONDS,
  });
}

export function clearSessionCookies(): void {
  const jar = cookies();
  jar.set(ACCESS_COOKIE, "", { path: "/", maxAge: 0 });
  jar.set(REFRESH_COOKIE, "", { path: "/", maxAge: 0 });
}

/**
 * Read the current user from cookies.
 *
 * Cheap path: cookie present + JWT not expired -> single GET /me.
 * Slow path: missing/expired access token but refresh token present ->
 * call /refresh, rewrite cookies, then GET /me.
 *
 * Never throws. Returns null on any failure and clears cookies if the
 * session is unrecoverable.
 */
export async function getCurrentUser(): Promise<PublicUser | null> {
  const jar = cookies();
  const at = jar.get(ACCESS_COOKIE)?.value ?? null;
  const rt = jar.get(REFRESH_COOKIE)?.value ?? null;

  if (at && jwtExpMs(at) - SKEW_MS > Date.now()) {
    const user = await fetchMe(at);
    if (user) return user;
    // 401 with a non-expired-looking JWT — token was revoked. Fall through
    // to the refresh path.
  }

  if (!rt) {
    if (at) clearSessionCookies();
    return null;
  }

  const refreshed = await refresh(rt);
  if (!refreshed) {
    clearSessionCookies();
    return null;
  }

  setSessionCookies(refreshed.access_token, refreshed.refresh_token, refreshed.expires_in);
  if (refreshed.user) return refreshed.user;
  const user = await fetchMe(refreshed.access_token);
  if (!user) {
    clearSessionCookies();
    return null;
  }
  return user;
}

/**
 * Server-component / server-action helper. Redirects to the sign-in page
 * if there is no current user. Throws a Next.js redirect — never returns
 * null.
 */
export async function requireUser(): Promise<PublicUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/app/sign-in");
  }
  return user;
}
