import "server-only";

/**
 * Authenticated server-side fetch helper.
 *
 * Intended only for server components and server actions. Reads the
 * access-token cookie, attaches it as a `Bearer` header, and calls the
 * internal API listener (`VOYAGENT_INTERNAL_API_URL`). Never throws —
 * returns `{ ok, status, data }` shaped like `lib/auth.ts::postJson`.
 *
 * If the access-token cookie is missing we redirect to `/sign-in`
 * immediately, since anything that calls this helper is inherently a
 * protected page. The middleware already bounces unauthenticated
 * traffic, so in practice this only fires when a cookie races with
 * expiry.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_COOKIE } from "./auth-shared";

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

export type ApiResult<T = unknown> = {
  ok: boolean;
  status: number;
  data: T | null;
};

async function readToken(): Promise<string> {
  const jar = await cookies();
  const at = jar.get(ACCESS_COOKIE)?.value ?? "";
  if (!at) {
    redirect("/sign-in");
  }
  return at;
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  const token = await readToken();
  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  try {
    const res = await fetch(`${apiBase()}${path}`, init);
    let data: unknown = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    return { ok: res.ok, status: res.status, data: data as T | null };
  } catch (err) {
    console.error("voyagent.api.request failed", { method, path, err });
    return { ok: false, status: 0, data: null };
  }
}

export async function apiGet<T = unknown>(path: string): Promise<ApiResult<T>> {
  return request<T>("GET", path);
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  return request<T>("POST", path, body ?? {});
}

export async function apiPatch<T = unknown>(
  path: string,
  body: unknown,
): Promise<ApiResult<T>> {
  return request<T>("PATCH", path, body);
}

/**
 * Pull a string "detail" field out of an API error body, if present.
 * FastAPI errors look like `{ "detail": "approval_already_resolved" }`
 * so this covers most of what the API surfaces to us.
 */
export function apiErrorCode(data: unknown): string | null {
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
