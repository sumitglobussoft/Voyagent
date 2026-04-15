// /app/approvals coverage.
//
// Approvals rows are created by the agent runtime, not the UI — we have
// no way to synthesise one end-to-end from the browser. So this spec
// only pins the read-side contract: empty state, filter query-params
// respected, and auth gating.

import { expect, test } from "../fixtures/authed";
import { test as base } from "@playwright/test";

test.describe("approvals — authenticated tenant", () => {
  test("empty state renders heading + pending/resolved sections", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/approvals", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { level: 1, name: /approvals/i }))
      .toBeVisible();
    await expect(page.getByText(/0 pending/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /^pending$/i })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /recently resolved/i }),
    ).toBeVisible();

    // Empty placeholders — page renders "Nothing here." when both sections
    // have zero rows.
    await expect(page.getByText(/nothing here/i).first()).toBeVisible();
  });

  test("?status=all renders without crash in a fresh tenant", async ({
    authedPage: page,
    apiRequest,
  }) => {
    await page.goto("/app/approvals?status=all", {
      waitUntil: "domcontentloaded",
    });
    await expect(page.getByRole("heading", { level: 1, name: /approvals/i }))
      .toBeVisible();

    // Confirm the API agrees the list is empty (belt + braces).
    const res = await apiRequest.get("/api/approvals?limit=50&offset=0");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { total?: number };
    expect(body.total).toBe(0);
  });

  test("?status=pending renders and shows zero pending", async ({
    authedPage: page,
  }) => {
    await page.goto("/app/approvals?status=pending", {
      waitUntil: "domcontentloaded",
    });
    await expect(page.getByText(/0 pending/i)).toBeVisible();
  });
});

// Unauthenticated probe does not need the `authedPage` fixture.
base.describe("approvals — gating", () => {
  base("unauth /app/approvals redirects to sign-in", async ({ page }) => {
    // The middleware strips the originating path, so we land on the bare
    // /app/sign-in (no `next=` query param). The sign-in form itself has
    // a hardcoded post-auth destination of /chat, so deep-linking via
    // `next=` is currently not wired end-to-end — flagged as a product
    // follow-up, not a gate regression.
    await page.goto("/app/approvals", { waitUntil: "domcontentloaded" });
    const u = page.url();
    expect(u).toContain("/app/sign-in");
  });
});
