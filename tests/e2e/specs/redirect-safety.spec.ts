// Open-redirect safety tests for the /app/sign-in and /app/sign-up
// flows. The auth forms ferry a `?next=` query through to the server
// action; if that value is ever accepted unchecked an attacker can
// turn the auth surfaces into a redirector:
//
//   /app/sign-in?next=//evil.com  -> sign in -> Location: //evil.com
//
// `apps/web/lib/next-url.ts::safeNextPath()` rejects everything that
// isn't a single-slash internal path. Each test below exercises one
// historically dangerous shape and asserts we land on the safe
// default (`/chat`) on the Voyagent host instead of following the
// attacker's URL off-domain.
//
// All tests provision a throwaway @mailinator.com user so we never
// pollute the shared demo account's session.

import { expect, test } from "@playwright/test";

import { uniqueEmail } from "../fixtures/authed";

type Case = {
  label: string;
  // Raw `next` value as it would appear pre-URL-encoding in the address bar.
  nextRaw: string;
  // true if safeNextPath() should REJECT this value and fall back to /chat.
  shouldReject: boolean;
};

const HOSTILE_CASES: Case[] = [
  { label: "//evil.com", nextRaw: "//evil.com", shouldReject: true },
  { label: "https://evil.com", nextRaw: "https://evil.com", shouldReject: true },
  { label: "javascript:alert(1)", nextRaw: "javascript:alert(1)", shouldReject: true },
  // `/etc/passwd` is a structurally valid internal path — safeNextPath()
  // permits it. The route will 404 on Next, but that's fine; the
  // essential guarantee is "never escape the host". We assert the final
  // URL stays on the configured baseURL host regardless.
  { label: "/etc/passwd", nextRaw: "/etc/passwd", shouldReject: false },
];

// Extract the host from the final page URL and compare against the
// configured baseURL host. This is the load-bearing assertion: no
// matter what, we must not have hopped off-domain.
function expectSameHost(pageUrl: string, baseUrl: string) {
  const got = new URL(pageUrl).host;
  const want = new URL(baseUrl).host;
  expect(got, `expected final host ${want}, got ${got} (${pageUrl})`).toBe(
    want,
  );
}

async function signUpFresh(
  page: import("@playwright/test").Page,
  prefix: string,
): Promise<{ email: string; password: string }> {
  const email = uniqueEmail(prefix);
  const password = "PlaywrightPass123!";
  await page.goto("/app/sign-up", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Full name").fill("Playwright RedirectSafety");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Agency name").fill("Playwright UI Agency");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await Promise.all([
    page.waitForURL(/\/app\/chat(\?|$)/, { timeout: 15_000 }),
    page.getByRole("button", { name: /create account/i }).click(),
  ]);
  // Clear the session cookies directly rather than clicking the
  // sign-out button. On mobile viewports the sign-out button is
  // behind an element that intercepts pointer events; the goal of
  // these tests is the redirect safety of the sign-in form, not the
  // sign-out UI. Cookie wipe is equivalent from the server's POV.
  await page.context().clearCookies();
  return { email, password };
}

test.describe("open-redirect safety", () => {
  for (const c of HOSTILE_CASES) {
    test(`sign-in: next=${c.label} stays on-host`, async ({
      page,
      baseURL,
    }) => {
      expect(baseURL, "baseURL must be configured").toBeTruthy();
      const { email, password } = await signUpFresh(page, "redir-signin");

      // URL-encode the hostile value so the browser actually ships what
      // we intend (e.g. `//evil.com` survives as a single `next` value
      // rather than turning into a path segment).
      const encoded = encodeURIComponent(c.nextRaw);
      await page.goto(`/app/sign-in?next=${encoded}`, {
        waitUntil: "domcontentloaded",
      });
      await page.getByLabel("Email").fill(email);
      await page.getByLabel("Password").fill(password);
      await page.getByRole("button", { name: /^sign in$/i }).click();

      // Wait for the post-submit navigation to settle. We do NOT wait
      // for a specific URL shape — the whole point is to catch any
      // off-host redirect, including ones we didn't anticipate.
      await page.waitForLoadState("domcontentloaded");
      // Give any chained client-side redirect a beat to land.
      await page.waitForLoadState("networkidle").catch(() => {});

      expectSameHost(page.url(), baseURL!);

      if (c.shouldReject) {
        // Rejected values fall back to the /chat default.
        await expect(page).toHaveURL(/\/app\/chat(\?|$)/);
      } else {
        // A structurally valid but non-existent internal path is
        // permitted. The essential property is "stayed on host"
        // (asserted above); accept any resulting page.
      }
    });
  }

  for (const c of HOSTILE_CASES) {
    test(`sign-up: next=${c.label} stays on-host`, async ({
      page,
      baseURL,
    }) => {
      expect(baseURL, "baseURL must be configured").toBeTruthy();
      const email = uniqueEmail("redir-signup");
      const password = "PlaywrightPass123!";
      const encoded = encodeURIComponent(c.nextRaw);

      await page.goto(`/app/sign-up?next=${encoded}`, {
        waitUntil: "domcontentloaded",
      });
      await page.getByLabel("Full name").fill("Playwright RedirSignup");
      await page.getByLabel("Work email").fill(email);
      await page.getByLabel("Agency name").fill("Playwright UI Agency");
      await page.getByLabel("Password", { exact: true }).fill(password);
      await page.getByLabel("Confirm password").fill(password);
      await page.getByRole("button", { name: /create account/i }).click();

      await page.waitForLoadState("domcontentloaded");
      await page.waitForLoadState("networkidle").catch(() => {});

      expectSameHost(page.url(), baseURL!);

      if (c.shouldReject) {
        // Rejected values fall back to the /chat default (welcome variant
        // for fresh sign-ups: `/chat?welcome=1`, but may also be plain
        // `/chat` depending on server-action behaviour — accept either).
        await expect(page).toHaveURL(/\/app\/chat(\?|$)/);
      }
    });
  }
});
