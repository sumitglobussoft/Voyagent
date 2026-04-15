/**
 * VoyagentAuth — cookie-free mobile auth client for the Voyagent API.
 *
 * Mirrors the API contract in apps/web/lib/auth.ts but stores tokens in
 * expo-secure-store (no cookies available on React Native). Exposes both
 * imperative helpers (for callers outside React) and a React context +
 * `useAuth()` hook consumed by screens.
 *
 * Token refresh: callers go through `getAccessToken()`, which decodes the
 * JWT's `exp` and pre-emptively calls `/api/auth/refresh` when fewer than
 * 30 seconds remain. A single in-flight refresh promise is shared across
 * concurrent callers so we never fire two refreshes for the same token.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { TokenStore } from "./tokenCache";
import type {
  ApiError,
  AuthResponse,
  PublicUser,
  SignInInput,
  SignUpInput,
} from "./auth-types";

const SKEW_MS = 30_000;

function apiBase(): string {
  const url = process.env.EXPO_PUBLIC_VOYAGENT_API_URL;
  if (typeof url === "string" && url.length > 0) return url;
  return "http://localhost:8000";
}

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  // `atob` is available in modern RN (Hermes) and Expo SDK 51.
  return globalThis.atob(padded + pad);
}

export function jwtExpMs(token: string): number {
  try {
    const parts = token.split(".");
    const body = parts[1];
    if (!body) return 0;
    const payload = JSON.parse(base64UrlDecode(body)) as { exp?: number };
    if (typeof payload.exp !== "number") return 0;
    return payload.exp * 1000;
  } catch {
    return 0;
  }
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
    });
    const text = await res.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    console.error("voyagent.auth.postJson failed", path, err);
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

async function persist(auth: AuthResponse): Promise<void> {
  await TokenStore.setAccessToken(auth.access_token);
  await TokenStore.setRefreshToken(auth.refresh_token);
  if (auth.user) await TokenStore.setUser(auth.user);
}

// Shared in-flight refresh so concurrent callers coalesce onto one request.
let refreshInFlight: Promise<AuthResponse | null> | null = null;

async function signUp(input: SignUpInput): Promise<AuthResponse | ApiError> {
  const res = await postJson("/api/auth/sign-up", input);
  if (res.ok) {
    const auth = asAuthResponse(res.data);
    if (auth) {
      await persist(auth);
      return auth;
    }
    return { error: "invalid_response" };
  }
  return { error: extractDetail(res.data) ?? "request_failed" };
}

async function signIn(input: SignInInput): Promise<AuthResponse | ApiError> {
  const res = await postJson("/api/auth/sign-in", input);
  if (res.ok) {
    const auth = asAuthResponse(res.data);
    if (auth) {
      await persist(auth);
      return auth;
    }
    return { error: "invalid_response" };
  }
  return { error: extractDetail(res.data) ?? "request_failed" };
}

async function refresh(): Promise<AuthResponse | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async (): Promise<AuthResponse | null> => {
    try {
      const rt = await TokenStore.getRefreshToken();
      if (!rt) return null;
      const res = await postJson("/api/auth/refresh", { refresh_token: rt });
      if (!res.ok) return null;
      const auth = asAuthResponse(res.data);
      if (!auth) return null;
      await persist(auth);
      return auth;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function signOut(): Promise<void> {
  const at = await TokenStore.getAccessToken();
  const rt = await TokenStore.getRefreshToken();
  const headers: Record<string, string> = {};
  if (at) headers.Authorization = `Bearer ${at}`;
  try {
    await postJson("/api/auth/sign-out", { refresh_token: rt }, headers);
  } finally {
    await TokenStore.clear();
  }
}

async function fetchMe(accessToken?: string): Promise<PublicUser | null> {
  const token = accessToken ?? (await TokenStore.getAccessToken());
  if (!token) return null;
  try {
    const res = await fetch(`${apiBase()}/api/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    return asPublicUser(data);
  } catch (err) {
    console.error("voyagent.auth.fetchMe failed", err);
    return null;
  }
}

async function getAccessToken(): Promise<string | null> {
  const current = await TokenStore.getAccessToken();
  if (current && jwtExpMs(current) - SKEW_MS > Date.now()) {
    return current;
  }
  const refreshed = await refresh();
  if (refreshed) return refreshed.access_token;
  return null;
}

export const VoyagentAuth = {
  signUp,
  signIn,
  signOut,
  refresh,
  fetchMe,
  getAccessToken,
};

// -------- React context --------

type AuthContextValue = {
  user: PublicUser | null;
  loading: boolean;
  signIn: (input: SignInInput) => Promise<ApiError | null>;
  signUp: (input: SignUpInput) => Promise<ApiError | null>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): ReactElement {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const hydrate = useCallback(async (): Promise<void> => {
    const cached = await TokenStore.getUser();
    if (cached && mounted.current) setUser(cached);

    const token = await getAccessToken();
    if (!token) {
      if (mounted.current) {
        setUser(null);
        setLoading(false);
      }
      await TokenStore.clear();
      return;
    }
    const me = await fetchMe(token);
    if (!me) {
      await TokenStore.clear();
      if (mounted.current) {
        setUser(null);
        setLoading(false);
      }
      return;
    }
    await TokenStore.setUser(me);
    if (mounted.current) {
      setUser(me);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      async signIn(input: SignInInput): Promise<ApiError | null> {
        const res = await signIn(input);
        if ("error" in res) return res;
        setUser(res.user ?? (await fetchMe(res.access_token)));
        return null;
      },
      async signUp(input: SignUpInput): Promise<ApiError | null> {
        const res = await signUp(input);
        if ("error" in res) return res;
        setUser(res.user ?? (await fetchMe(res.access_token)));
        return null;
      },
      async signOut(): Promise<void> {
        await signOut();
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
