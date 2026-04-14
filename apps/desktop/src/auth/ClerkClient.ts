/**
 * Thin wrapper over `@clerk/clerk-js` configured for the Voyagent desktop
 * shell. Clerk does not ship a first-party Tauri SDK, so we drive the
 * "headless" JS SDK ourselves:
 *
 *  1. Sign-in opens the Clerk hosted URL in the OS browser via
 *     `@tauri-apps/plugin-shell.open`.
 *  2. The user completes the flow; Clerk redirects to
 *     `voyagent://auth/callback?session=<token>` (configured in the Clerk
 *     dashboard as an allowed redirect URL for the desktop instance).
 *  3. `DeepLinkHandler` captures the session token from the redirect and
 *     calls `ClerkClient.applySession(token)` which forwards to the Clerk
 *     SDK's `setActive` equivalent.
 *  4. On subsequent launches we rehydrate the stored token; the SDK
 *     refreshes it against Clerk's Frontend API before the first API call.
 *
 * Notes:
 *  - We NEVER log token contents. `console.warn` is OK for flow markers.
 *  - All public methods are `async` so higher layers can `await` without
 *    adjusting once we swap in a real Clerk refresh path.
 */
import { Clerk } from "@clerk/clerk-js";
import { open as openUrl } from "@tauri-apps/plugin-shell";

import { tokenStore } from "./tokenStore.js";

export interface DesktopUser {
  id: string;
  email: string | null;
  fullName: string | null;
}

export interface ClerkClientOptions {
  publishableKey: string;
  /**
   * Deep-link URI the Clerk dashboard sends the user to after sign-in.
   * Must be registered as an allowed redirect URL in the Clerk instance.
   */
  redirectUri: string;
}

export class ClerkClient {
  readonly #clerk: Clerk;
  readonly #redirectUri: string;
  #ready = false;

  constructor(opts: ClerkClientOptions) {
    this.#clerk = new Clerk(opts.publishableKey);
    this.#redirectUri = opts.redirectUri;
  }

  /**
   * Loads Clerk and rehydrates any stored session token. Safe to call
   * more than once — repeats are no-ops.
   */
  async init(): Promise<void> {
    if (this.#ready) return;
    await this.#clerk.load();

    const stored = await tokenStore.get();
    if (stored !== null) {
      try {
        // The JS SDK accepts a session JWT via `setSession` in Clerk v5.
        // If it rejects (expired + unrefreshable), we clear and fall
        // through to a signed-out state.
        await this.#clerk.setActive?.({ session: stored.token });
      } catch {
        await tokenStore.clear();
      }
    }
    this.#ready = true;
  }

  get isAuthenticated(): boolean {
    return Boolean(this.#clerk.session);
  }

  get user(): DesktopUser | null {
    const u = this.#clerk.user;
    if (!u) return null;
    return {
      id: u.id,
      email: u.primaryEmailAddress?.emailAddress ?? null,
      fullName: u.fullName ?? null,
    };
  }

  /**
   * Fetches a fresh session JWT. The Clerk SDK refreshes internally as
   * needed. Returns `null` when signed out.
   */
  async getToken(): Promise<string | null> {
    if (!this.#clerk.session) return null;
    const token = await this.#clerk.session.getToken();
    return token ?? null;
  }

  /**
   * Opens the Clerk hosted sign-in URL in the OS browser. The deep-link
   * handler will call `applySession` when the redirect lands.
   */
  async signIn(): Promise<void> {
    const signInUrl = this.#buildHostedSignInUrl();
    await openUrl(signInUrl);
  }

  async signOut(): Promise<void> {
    try {
      await this.#clerk.signOut();
    } finally {
      await tokenStore.clear();
    }
  }

  /**
   * Wire up a session captured from the deep-link redirect. Persists the
   * token so the next launch can rehydrate.
   */
  async applySession(token: string): Promise<void> {
    await this.#clerk.setActive?.({ session: token });
    await tokenStore.set(token);
  }

  #buildHostedSignInUrl(): string {
    // Clerk's hosted sign-in URL is derived from the frontend API origin
    // the SDK was configured with. We append `redirect_url` so Clerk
    // sends the user back to our deep-link scheme after success.
    const base =
      (this.#clerk as unknown as { frontendApi?: string }).frontendApi ??
      "https://clerk.voyagent.example";
    const url = new URL("/sign-in", base);
    url.searchParams.set("redirect_url", this.#redirectUri);
    return url.toString();
  }
}
