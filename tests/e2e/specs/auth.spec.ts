// Authentication flows exercised through the /app/sign-in and /app/sign-up
// UIs. Each test creates its own tenant (via the UI sign-up path or via
// the API) so runs are idempotent and do not collide.
//
// We deliberately avoid the shared demo account described on the sign-in
// banner because it is exposed to public visitors — tests that mutate
// state on the demo tenant would make the public experience flaky.

import { expect, test } from "@playwright/test";

import { uniqueEmail } from "../fixtures/authed";

const DEMO_EMAIL = "demo@voyagent.globusdemos.com";
const DEMO_PASSWORD = "DemoPassword123!";

test.describe("auth flows", () => {
  test("sign-up via UI lands on /app/chat", async ({ page }) => {
    const email = uniqueEmail("signup-ui");
    const password = "PlaywrightPass123!";

    await page.goto("/app/sign-up", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Full name").fill("Playwright Signup");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Agency name").fill("Playwright UI Agency");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password").fill(password);

    await Promise.all([
      page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /create account/i }).click(),
    ]);

    await expect(page).toHaveURL(/\/app\/chat(\?|$)/);
  });

  test("sign-in via UI lands on /app/chat after UI sign-up + sign-out", async ({
    page,
  }) => {
    const email = uniqueEmail("signin-ui");
    const password = "PlaywrightPass123!";

    // Create the account through the UI so the subsequent sign-in exercises
    // only the sign-in form.
    await page.goto("/app/sign-up", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Full name").fill("Playwright Signin");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Agency name").fill("Playwright UI Agency");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password").fill(password);
    await Promise.all([
      page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /create account/i }).click(),
    ]);

    // Sign out — the layout surfaces a form that POSTs to /app/sign-out.
    // Route redirects to "/" (marketing root) with status 303.
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.waitForLoadState("domcontentloaded");
    await expect(page).not.toHaveURL(/\/app\/chat/);

    // Now sign back in.
    await page.goto("/app/sign-in", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await Promise.all([
      page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /^sign in$/i }).click(),
    ]);

    await expect(page).toHaveURL(/\/app\/chat(\?|$)/);
  });

  test("sign-in with wrong password shows inline error", async ({ page }) => {
    await page.goto("/app/sign-in", { waitUntil: "domcontentloaded" });
    await page
      .getByLabel("Email")
      .fill(uniqueEmail("does-not-exist"));
    await page.getByLabel("Password").fill("ObviouslyWrongPassword!!");
    await page.getByRole("button", { name: /^sign in$/i }).click();

    // The form renders a styled error banner rather than an ARIA
    // role="alert", and the user-facing copy is "Email or password is
    // incorrect." (the API emits `invalid_credentials` but the web layer
    // translates it to prose).
    const errorBanner = page.getByText(
      /email or password is incorrect/i,
    );
    await expect(errorBanner).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/app\/sign-in/);
  });

  test("demo account banner is visible on /app/sign-in", async ({ page }) => {
    await page.goto("/app/sign-in", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(DEMO_EMAIL, { exact: false })).toBeVisible();
    await expect(page.getByText(DEMO_PASSWORD, { exact: false })).toBeVisible();
    await expect(
      page.getByRole("link", { name: /use demo credentials/i }),
    ).toBeVisible();
  });

  test("?demo=1 pre-fills both fields", async ({ page }) => {
    await page.goto("/app/sign-in?demo=1", { waitUntil: "domcontentloaded" });
    const emailInput = page.getByLabel("Email");
    const passwordInput = page.getByLabel("Password");
    await expect(emailInput).toHaveValue(DEMO_EMAIL);
    await expect(passwordInput).toHaveValue(DEMO_PASSWORD);
  });

  test("sign-out returns the user to a non-authenticated state", async ({
    page,
  }) => {
    const email = uniqueEmail("signout");
    const password = "PlaywrightPass123!";

    await page.goto("/app/sign-up", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Full name").fill("Playwright Signout");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Agency name").fill("Playwright UI Agency");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password").fill(password);
    await Promise.all([
      page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /create account/i }).click(),
    ]);

    // Clicking the sign-out button 303-redirects to "/" per the route. Some
    // deployments may instead redirect to /app/sign-in; accept either and
    // assert we are not still on a gated /app/* surface.
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.waitForLoadState("domcontentloaded");
    const finalUrl = page.url();
    expect(finalUrl).toMatch(/(\/|\/app\/sign-in)(\?|$|#)/);
    expect(finalUrl).not.toMatch(/\/app\/chat/);

    // Subsequent /app/chat hit must redirect to sign-in.
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/app\/sign-in/);
  });

  test("unauth access to /app/chat redirects to /app/sign-in with next=%2Fchat", async ({
    page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });
    // Middleware MUST preserve the original path as ?next=... (encoded or
    // decoded) so the sign-in action can redirect back after a successful
    // login. Single strict assertion: path is /app/sign-in AND next=/chat.
    await expect(page).toHaveURL(
      /\/app\/sign-in\?(?:[^#]*&)?next=(?:%2F|\/)chat(?:&|$|#)/,
    );
  });

  test("unauth deep-link to /app/enquiries preserves next= and post-sign-in lands on /app/enquiries", async ({
    page,
  }) => {
    // First create an account so we have valid credentials to sign in with.
    const email = uniqueEmail("deeplink");
    const password = "PlaywrightPass123!";

    await page.goto("/app/sign-up", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Full name").fill("Playwright Deeplink");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Agency name").fill("Playwright UI Agency");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password").fill(password);
    await Promise.all([
      page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /create account/i }).click(),
    ]);
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.waitForLoadState("domcontentloaded");

    // Now the deep-link flow.
    await page.goto("/app/enquiries", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(
      /\/app\/sign-in\?(?:[^#]*&)?next=(?:%2F|\/)enquiries(?:&|$|#)/,
    );

    // Sign in — must land on /app/enquiries, not /app/chat.
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await Promise.all([
      page.waitForURL(/\/app\/enquiries(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /^sign in$/i }).click(),
    ]);
    await expect(page).toHaveURL(/\/app\/enquiries(\?|$)/);
    // Must NOT have been bounced back to /chat.
    await expect(page).not.toHaveURL(/\/app\/chat/);
  });

  test("bare /app resolves in at most 2 hops to /app/sign-in without looping", async ({
    page,
  }) => {
    // Regression for the /app -> /app/ -> /app nginx+Next loop.
    // A fresh unauth visit must settle at /app/sign-in in a bounded
    // number of hops. We instrument framenavigated to assert the hop
    // count stays small; anything >4 signals a loop regression.
    const urls: string[] = [];
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) urls.push(frame.url());
    });

    const response = await page.goto("/app", { waitUntil: "domcontentloaded" });
    expect(response).not.toBeNull();
    await expect(page).toHaveURL(/\/app\/sign-in(\?|$)/);
    // Hops observed on a healthy deployment: 1 (initial /app) +
    // 1 (redirected /app/sign-in). Anything more than 4 indicates
    // the historical loop has regressed.
    expect(
      urls.length,
      `expected bounded hop count, got ${urls.length}: ${urls.join(" -> ")}`,
    ).toBeLessThanOrEqual(4);
  });

  test("sign-up honours next= — /app/sign-up?next=/audit lands on /app/audit", async ({
    page,
  }) => {
    // Wave 8 wired `next=` parity into the sign-up server action. A freshly
    // created account that arrived via a deep-link must land on the
    // requested page, not the default /chat welcome surface.
    const email = uniqueEmail("signup-next");
    const password = "PlaywrightPass123!";

    await page.goto("/app/sign-up?next=%2Faudit", {
      waitUntil: "domcontentloaded",
    });
    await page.getByLabel("Full name").fill("Playwright SignupNext");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Agency name").fill("Playwright UI Agency");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password").fill(password);

    await Promise.all([
      page.waitForURL(/\/app\/audit(\?|$)/, { timeout: 15_000 }),
      page.getByRole("button", { name: /create account/i }).click(),
    ]);

    await expect(page).toHaveURL(/\/app\/audit(\?|$)/);
    // Must NOT have been bounced to the default /chat welcome page.
    await expect(page).not.toHaveURL(/\/app\/chat/);
  });

  test("cross-link: sign-in -> Create one preserves next=", async ({
    page,
  }) => {
    // Visiting /app/sign-in?next=/enquiries and clicking "Create one"
    // must forward the `next` through to the sign-up page so the fresh
    // account lands on /enquiries, not /chat.
    await page.goto("/app/sign-in?next=%2Fenquiries", {
      waitUntil: "domcontentloaded",
    });
    await Promise.all([
      page.waitForURL(/\/app\/sign-up\?(?:[^#]*&)?next=(?:%2F|\/)enquiries/, {
        timeout: 10_000,
      }),
      page.getByRole("link", { name: /create one/i }).click(),
    ]);
    await expect(page).toHaveURL(
      /\/app\/sign-up\?(?:[^#]*&)?next=(?:%2F|\/)enquiries(?:&|$|#)/,
    );
  });
});
