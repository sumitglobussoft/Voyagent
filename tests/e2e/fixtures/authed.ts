// Shared Playwright fixtures for authenticated flows.
//
// Every authed spec depends on a fresh tenant so test data never leaks
// between workers or runs. We sign up a brand-new user via the API (faster
// and more deterministic than driving the UI sign-up form) and expose:
//
//   - `authedUser`    : credentials, tokens, and the user payload returned
//                       by POST /api/auth/sign-up
//   - `authedPage`    : a `Page` that already has the `voyagent_at` cookie
//                       set, so navigation to `/app/*` renders instead of
//                       redirecting to /sign-in
//   - `apiRequest`    : an `APIRequestContext` pre-bound with the access
//                       token in an Authorization header so specs can
//                       seed state or exercise pure JSON endpoints
//
// Emails use `@mailinator.com` — RFC 2606's `.test` TLD is rejected by the
// API's pydantic email-validator.

import {
  test as base,
  expect,
  request as playwrightRequest,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const DEFAULT_BASE_URL = "https://voyagent.globusdemos.com";

function baseURL(): string {
  return (process.env.VOYAGENT_BASE_URL ?? DEFAULT_BASE_URL).replace(
    /\/+$/,
    "",
  );
}

/**
 * Derive the cookie domain from the configured base URL so the
 * `voyagent_at` cookie pre-seed works against arbitrary deployments.
 */
function cookieDomain(): string {
  try {
    return new URL(baseURL()).hostname;
  } catch {
    return "voyagent.globusdemos.com";
  }
}

export type SignUpPayload = {
  email: string;
  password: string;
  full_name: string;
  agency_name: string;
};

export type AuthedUser = {
  email: string;
  password: string;
  fullName: string;
  agencyName: string;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: {
    id: string;
    email: string;
    tenant_id: string;
    tenant_name?: string;
    full_name?: string | null;
    role?: string;
    created_at?: string;
  };
};

/**
 * Generate a unique @mailinator.com address. We intentionally avoid the
 * RFC 2606 reserved `.test` TLD because the API's email-validator treats
 * it as non-deliverable and rejects sign-ups.
 */
export function uniqueEmail(prefix = "playwright"): string {
  const rnd = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now()}-${rnd}@mailinator.com`;
}

/**
 * Create a fresh user directly through the API. Returns the raw response
 * body plus the credentials used so specs can sign in through the UI too.
 */
export async function createUserViaApi(
  apiCtx: APIRequestContext,
  overrides: Partial<SignUpPayload> = {},
): Promise<AuthedUser> {
  const payload: SignUpPayload = {
    email: overrides.email ?? uniqueEmail(),
    password: overrides.password ?? "PlaywrightPass123!",
    full_name: overrides.full_name ?? "Playwright Tester",
    agency_name: overrides.agency_name ?? "Playwright Test Agency",
  };

  const res = await apiCtx.post("/api/auth/sign-up", {
    data: payload,
    headers: { "content-type": "application/json" },
    failOnStatusCode: false,
  });
  const status = res.status();
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  expect(
    status === 200 || status === 201,
    `sign-up API returned ${status}: ${JSON.stringify(body).slice(0, 200)}`,
  ).toBe(true);

  const accessToken =
    typeof body.access_token === "string" ? body.access_token : "";
  const refreshToken =
    typeof body.refresh_token === "string" ? body.refresh_token : "";
  const expiresIn =
    typeof body.expires_in === "number" ? body.expires_in : 3600;
  expect(accessToken, "sign-up response missing access_token").not.toBe("");
  expect(refreshToken, "sign-up response missing refresh_token").not.toBe("");

  const user = (body.user ?? {}) as AuthedUser["user"];
  expect(typeof user.id === "string" && user.id.length > 0).toBe(true);
  expect(typeof user.tenant_id === "string" && user.tenant_id.length > 0).toBe(
    true,
  );

  return {
    email: payload.email,
    password: payload.password,
    fullName: payload.full_name,
    agencyName: payload.agency_name,
    accessToken,
    refreshToken,
    expiresIn,
    user,
  };
}

type AuthedFixtures = {
  authedUser: AuthedUser;
  authedPage: Page;
  apiRequest: APIRequestContext;
};

/**
 * Extended Playwright `test` with auth-aware fixtures.
 *
 * - `authedUser`  — creates a fresh user (and tenant) per test.
 * - `apiRequest`  — request context bound to `VOYAGENT_BASE_URL` with the
 *   fresh user's bearer token. Disposed automatically at end of test.
 * - `authedPage`  — the default `page`, with `voyagent_at` pre-injected so
 *   the very first navigation to `/app/*` already renders the product UI.
 */
export const test = base.extend<AuthedFixtures>({
  // eslint-disable-next-line no-empty-pattern
  authedUser: async ({}, use) => {
    const signupCtx = await playwrightRequest.newContext({
      baseURL: baseURL(),
      ignoreHTTPSErrors: false,
    });
    try {
      const user = await createUserViaApi(signupCtx);
      await use(user);
    } finally {
      await signupCtx.dispose();
    }
  },

  apiRequest: async ({ authedUser }, use) => {
    const ctx = await playwrightRequest.newContext({
      baseURL: baseURL(),
      extraHTTPHeaders: {
        Authorization: `Bearer ${authedUser.accessToken}`,
      },
      ignoreHTTPSErrors: false,
    });
    try {
      await use(ctx);
    } finally {
      await ctx.dispose();
    }
  },

  authedPage: async ({ page, authedUser }, use) => {
    const domain = cookieDomain();
    await page.context().addCookies([
      {
        name: "voyagent_at",
        value: authedUser.accessToken,
        domain,
        path: "/",
        httpOnly: false,
        secure: baseURL().startsWith("https://"),
        sameSite: "Lax",
      },
      {
        name: "voyagent_rt",
        value: authedUser.refreshToken,
        domain,
        path: "/",
        httpOnly: false,
        secure: baseURL().startsWith("https://"),
        sameSite: "Lax",
      },
    ]);
    await use(page);
  },
});

export { expect };
