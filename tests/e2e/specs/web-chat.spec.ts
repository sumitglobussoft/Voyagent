// Smoke for the authenticated /app/chat surface.
//
// Pinning the live agent's reply is flaky (depends on ANTHROPIC_API_KEY
// on the server), so this spec only asserts that:
//
//   - the composer textarea is present + enabled for a freshly-signed-in
//     user on a fresh tenant
//   - typing and submitting places the user message into the transcript
//
// The submit-half is gated behind CHAT_E2E_ENABLED so CI can opt in once
// the live agent is reliably wired.

import { expect, test } from "../fixtures/authed";

const CHAT_E2E_ENABLED =
  (process.env.CHAT_E2E_ENABLED ?? "").toLowerCase() === "true" ||
  process.env.CHAT_E2E_ENABLED === "1";

test.describe("web chat smoke", () => {
  test("composer textarea is visible and enabled", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });
    const composer = page.getByLabel("Message input");
    await expect(composer).toBeVisible({ timeout: 15_000 });
    await expect(composer).toBeEnabled();
  });

  test("submitting a message renders it in the transcript", async ({
    authedPage: page,
  }) => {
    test.skip(
      !CHAT_E2E_ENABLED,
      "CHAT_E2E_ENABLED is unset; live chat send is flaky without ANTHROPIC_API_KEY on the target.",
    );

    await page.goto("/app/chat", { waitUntil: "domcontentloaded" });
    const composer = page.getByLabel("Message input");
    await expect(composer).toBeVisible({ timeout: 15_000 });
    await expect(composer).toBeEnabled();

    const probe = `playwright probe ${Date.now()}`;
    await composer.fill(probe);
    await page.getByRole("button", { name: /^send$/i }).click();

    // The composer clears on submit; the typed text must surface somewhere
    // in the transcript area within a few seconds. We don't assert on the
    // agent's reply — that depends on ANTHROPIC_API_KEY wiring.
    await expect(page.getByText(probe, { exact: false })).toBeVisible({
      timeout: 5_000,
    });
  });
});
