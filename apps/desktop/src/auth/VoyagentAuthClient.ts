/**
 * In-house cookie/JWT auth client for the Voyagent desktop shell.
 *
 * Desktop is a native app — no HttpOnly cookies. Tokens live in the
 * OS-local secure store via `tokenStore` (Tauri command backed). This
 * class is the single seam through which the rest of the app reads or
 * mutates authentication state; other modules must go through
 * `AuthProvider` / `getAccessToken()`, never poke the store directly.
 *
 * Token refresh strategy: `getAccessToken()` checks the stored access
 * token's `exp` claim with a small skew and transparently calls
 * `/api/auth/refresh` using the refresh token when the JWT is close to
 * expiry or has been rejected by the server. A concurrent-call guard
 * collapses parallel refreshes onto one inflight promise.
 */
import { tokenStore, type StoredSession } from "./tokenStore.js";

export interface DesktopUser {
  id: string;
  email: string;
  fullName: string | null;
  role: string;
  tenantId: string;
  tenantName: string;
}

interface PublicUserWire {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tenant_id: string;
  tenant_name: string;
  created_at: string;
}

interface AuthResponseWire {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user?: PublicUserWire;
}

export interface SignUpInput {
  email: string;
  password: string;
  full_name: string;
  agency_name: string;
}

export interface SignInInput {
  email: string;
  password: string;
}

export class AuthError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "AuthError";
  }
}

const SKEW_MS = 30_000;

function toUser(wire: PublicUserWire): DesktopUser {
  return {
    id: wire.id,
    email: wire.email,
    fullName: wire.full_name,
    role: wire.role,
    tenantId: wire.tenant_id,
    tenantName: wire.tenant_name,
  };
}

function jwtExpMs(token: string): number {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return 0;
    const payloadB64 = parts[1]!.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(payloadB64);
    const payload = JSON.parse(json) as { exp?: number };
    if (typeof payload.exp !== "number") return 0;
    return payload.exp * 1000;
  } catch {
    return 0;
  }
}

export class VoyagentAuthClient {
  readonly #baseUrl: string;
  #session: StoredSession | null = null;
  #user: DesktopUser | null = null;
  #refreshInflight: Promise<string | null> | null = null;

  constructor(opts: { baseUrl: string }) {
    this.#baseUrl = opts.baseUrl.replace(/\/$/, "");
  }

  get user(): DesktopUser | null {
    return this.#user;
  }

  get isAuthenticated(): boolean {
    return this.#session !== null && this.#user !== null;
  }

  /**
   * Load any stored session from the secure store and validate it via
   * `/me`. If the access token is missing/rejected but a refresh token is
   * present, refresh transparently. On unrecoverable failure, clears the
   * store and returns without throwing.
   */
  async init(): Promise<void> {
    const stored = await tokenStore.get();
    if (stored === null) return;
    this.#session = stored;
    this.#user = stored.user ?? null;

    const token = await this.getAccessToken();
    if (token === null) {
      await this.#clearLocal();
      return;
    }
    const me = await this.#fetchMeWith(token);
    if (me === null) {
      // Token rejected server-side even after refresh. Clear.
      await this.#clearLocal();
      return;
    }
    this.#user = me;
    await this.#persist();
  }

  async signUp(input: SignUpInput): Promise<DesktopUser> {
    const wire = await this.#post<AuthResponseWire>("/api/auth/sign-up", input);
    return this.#acceptAuth(wire);
  }

  async signIn(input: SignInInput): Promise<DesktopUser> {
    const wire = await this.#post<AuthResponseWire>("/api/auth/sign-in", input);
    return this.#acceptAuth(wire);
  }

  async signOut(): Promise<void> {
    const refreshToken = this.#session?.refreshToken ?? null;
    const accessToken = this.#session?.accessToken ?? null;
    try {
      await fetch(`${this.#baseUrl}/api/auth/sign-out`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      /* best effort */
    }
    await this.#clearLocal();
  }

  async fetchMe(): Promise<DesktopUser | null> {
    const token = await this.getAccessToken();
    if (!token) return null;
    const me = await this.#fetchMeWith(token);
    if (me) {
      this.#user = me;
      await this.#persist();
    }
    return me;
  }

  /**
   * Returns a valid access token, refreshing if the current one is
   * expired (or close enough to expiry). Returns `null` if there is no
   * session or refresh fails — callers should treat that as signed out.
   */
  async getAccessToken(): Promise<string | null> {
    if (this.#session === null) return null;
    const exp = jwtExpMs(this.#session.accessToken);
    if (exp > Date.now() + SKEW_MS) {
      return this.#session.accessToken;
    }
    return this.#refresh();
  }

  async #refresh(): Promise<string | null> {
    if (this.#session === null) return null;
    if (this.#refreshInflight) return this.#refreshInflight;
    const refreshToken = this.#session.refreshToken;
    this.#refreshInflight = (async () => {
      try {
        const res = await fetch(`${this.#baseUrl}/api/auth/refresh`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          await this.#clearLocal();
          return null;
        }
        const wire = (await res.json()) as AuthResponseWire;
        const user = wire.user ? toUser(wire.user) : this.#user;
        this.#session = {
          accessToken: wire.access_token,
          refreshToken: wire.refresh_token,
          user,
        };
        this.#user = user;
        await this.#persist();
        return wire.access_token;
      } catch {
        return null;
      } finally {
        this.#refreshInflight = null;
      }
    })();
    return this.#refreshInflight;
  }

  async #fetchMeWith(token: string): Promise<DesktopUser | null> {
    try {
      const res = await fetch(`${this.#baseUrl}/api/auth/me`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
      });
      if (res.status === 401) {
        // Try one refresh, then retry once.
        const refreshed = await this.#refresh();
        if (!refreshed) return null;
        const retry = await fetch(`${this.#baseUrl}/api/auth/me`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${refreshed}`,
            Accept: "application/json",
          },
        });
        if (!retry.ok) return null;
        return toUser((await retry.json()) as PublicUserWire);
      }
      if (!res.ok) return null;
      return toUser((await res.json()) as PublicUserWire);
    } catch {
      return null;
    }
  }

  async #post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.#baseUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
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
    if (!res.ok) {
      const detail =
        (typeof data === "object" &&
          data !== null &&
          "detail" in data &&
          typeof (data as { detail: unknown }).detail === "string" &&
          (data as { detail: string }).detail) ||
        `request_failed_${res.status}`;
      throw new AuthError(detail, res.status);
    }
    return data as T;
  }

  async #acceptAuth(wire: AuthResponseWire): Promise<DesktopUser> {
    const user = wire.user ? toUser(wire.user) : null;
    this.#session = {
      accessToken: wire.access_token,
      refreshToken: wire.refresh_token,
      user,
    };
    this.#user = user;
    await this.#persist();
    if (this.#user) return this.#user;
    const me = await this.#fetchMeWith(wire.access_token);
    if (!me) throw new AuthError("me_lookup_failed", 0);
    this.#user = me;
    await this.#persist();
    return me;
  }

  async #persist(): Promise<void> {
    if (this.#session === null) return;
    await tokenStore.set({
      accessToken: this.#session.accessToken,
      refreshToken: this.#session.refreshToken,
      user: this.#user,
    });
  }

  async #clearLocal(): Promise<void> {
    this.#session = null;
    this.#user = null;
    await tokenStore.clear();
  }
}
