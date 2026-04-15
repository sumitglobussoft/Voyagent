// End-to-end coverage of the /app/enquiries surface.
//
// The `authedUser` / `authedPage` fixtures each give us a fresh tenant,
// which is load-bearing: the list, search, and promote-idempotency tests
// all assert on "exactly one" or "exactly this enquiry" in the tenant's
// data, so contamination from other tests would flake them.

import { expect, test } from "../fixtures/authed";

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function uniqueCustomerName(tag: string): string {
  // Long enough that `q=` matching is unambiguous even across concurrent runs.
  const rnd = Math.random().toString(36).slice(2, 10);
  return `QA ${tag} ${Date.now()}-${rnd}`;
}

test.describe("enquiries", () => {
  test("create enquiry via /app/enquiries/new and land on detail", async ({
    authedPage: page,
  }) => {
    const customer = uniqueCustomerName("create");
    await page.goto("/app/enquiries/new", { waitUntil: "domcontentloaded" });

    await page.getByLabel(/^customer name/i).fill(customer);
    await page.getByLabel(/^pax count/i).fill("3");
    await page.getByLabel("Origin").fill("BOM");
    await page.getByLabel("Destination").fill("DXB");
    await page.getByLabel("Depart date").fill("2026-10-01");
    await page.getByLabel("Return date").fill("2026-10-08");
    await page.getByLabel("Budget amount").fill("125000.00");
    await page.getByLabel("Currency").fill("INR");

    await Promise.all([
      page.waitForURL(new RegExp(`/app/enquiries/${UUID_RE.source}$`), {
        timeout: 15_000,
      }),
      page.getByRole("button", { name: /create enquiry/i }).click(),
    ]);

    expect(page.url()).toMatch(/\/app\/enquiries\//);
    await expect(
      page.getByRole("heading", { level: 1, name: customer }),
    ).toBeVisible();
    await expect(page.getByText("BOM → DXB")).toBeVisible();
    // Pax, budget and currency are rendered as plain text inside info items.
    await expect(page.getByText("3", { exact: true }).first()).toBeVisible();
  });

  test("list page shows the new enquiry and `q` search filters to one row", async ({
    authedPage: page,
    apiRequest,
  }) => {
    const customer = uniqueCustomerName("list");
    // Seed via the API — faster and keeps UI in the assertion path only.
    const create = await apiRequest.post("/api/enquiries", {
      data: {
        customer_name: customer,
        pax_count: 2,
        origin: "DEL",
        destination: "LHR",
      },
      failOnStatusCode: false,
    });
    expect(
      [200, 201].includes(create.status()),
      `seed failed: ${create.status()}`,
    ).toBe(true);

    await page.goto("/app/enquiries", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("link", { name: customer, exact: true }),
    ).toBeVisible();

    // Full-text search. Submit via the Apply button.
    await page.getByLabel("Search").fill(customer);
    await Promise.all([
      page.waitForLoadState("domcontentloaded"),
      page.getByRole("button", { name: /^apply$/i }).click(),
    ]);

    const matchingRows = page.getByRole("link", { name: customer, exact: true });
    await expect(matchingRows).toHaveCount(1);
  });

  test("edit notes and status on the detail page persists", async ({
    authedPage: page,
    apiRequest,
  }) => {
    const customer = uniqueCustomerName("edit");
    const seed = await apiRequest.post("/api/enquiries", {
      data: { customer_name: customer, pax_count: 1 },
      failOnStatusCode: false,
    });
    expect([200, 201].includes(seed.status())).toBe(true);
    const body = (await seed.json()) as { id?: string };
    expect(typeof body.id).toBe("string");
    const id = body.id as string;

    await page.goto(`/app/enquiries/${id}`, { waitUntil: "domcontentloaded" });

    const noteText = `seeded by playwright ${Date.now()}`;
    await page.getByLabel("Notes").fill(noteText);
    await page.getByRole("button", { name: /save changes/i }).click();
    await page.waitForLoadState("domcontentloaded");

    // Change status new -> quoted via the status <select>.
    await page.getByLabel("Status").selectOption("quoted");
    await page.getByRole("button", { name: /save status/i }).click();
    await page.waitForLoadState("domcontentloaded");

    // Reload and re-read to prove persistence.
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("Notes")).toHaveValue(noteText);
    await expect(page.getByLabel("Status")).toHaveValue("quoted");
  });

  test("status regression new->booked->new is rejected and stays booked", async ({
    authedPage: page,
    apiRequest,
  }) => {
    const customer = uniqueCustomerName("status-regress");
    const seed = await apiRequest.post("/api/enquiries", {
      data: { customer_name: customer, pax_count: 1 },
      failOnStatusCode: false,
    });
    expect([200, 201].includes(seed.status())).toBe(true);
    const id = ((await seed.json()) as { id: string }).id;

    // Walk new -> quoted -> booked, then try to regress to new.
    // booked is a terminal state; once there the page replaces the select
    // with a message, so we have to drive the first two transitions via
    // the UI and the regression attempt via a direct status PATCH against
    // the API (the only way to even send "new" from "booked").
    await page.goto(`/app/enquiries/${id}`, { waitUntil: "domcontentloaded" });
    await page.getByLabel("Status").selectOption("quoted");
    await page.getByRole("button", { name: /save status/i }).click();
    await page.waitForLoadState("domcontentloaded");

    await page.getByLabel("Status").selectOption("booked");
    await page.getByRole("button", { name: /save status/i }).click();
    await page.waitForLoadState("domcontentloaded");

    // Enquiry is booked — UI surfaces the terminal-state message and no
    // status <select> is rendered.
    await expect(
      page.getByText(/no further transitions are allowed/i),
    ).toBeVisible();

    // Ask the API to regress to new. The contract is a 400.
    const regress = await apiRequest.patch(`/api/enquiries/${id}/status`, {
      data: { status: "new" },
      failOnStatusCode: false,
    });
    expect(regress.status()).toBe(400);

    // And the persisted status is still booked.
    const check = await apiRequest.get(`/api/enquiries/${id}`);
    expect(check.status()).toBe(200);
    const checkBody = (await check.json()) as { status?: string };
    expect(checkBody.status).toBe("booked");
  });

  test("two-step cancel via ?confirm=1 transitions to cancelled", async ({
    authedPage: page,
    apiRequest,
  }) => {
    const customer = uniqueCustomerName("cancel");
    const seed = await apiRequest.post("/api/enquiries", {
      data: { customer_name: customer, pax_count: 1 },
      failOnStatusCode: false,
    });
    expect([200, 201].includes(seed.status())).toBe(true);
    const id = ((await seed.json()) as { id: string }).id;

    await page.goto(`/app/enquiries/${id}`, { waitUntil: "domcontentloaded" });

    // First click arms confirmation — the action redirects back with ?confirm=1.
    await page.getByRole("button", { name: /^cancel enquiry$/i }).click();
    await page.waitForURL(/\?confirm=1/, { timeout: 10_000 });

    // Second click actually cancels.
    await page
      .getByRole("button", { name: /click again to confirm cancel/i })
      .click();
    await page.waitForLoadState("domcontentloaded");

    const check = await apiRequest.get(`/api/enquiries/${id}`);
    expect(check.status()).toBe(200);
    const body = (await check.json()) as { status?: string };
    expect(body.status).toBe("cancelled");
  });

  test("promote-to-chat is idempotent and returns the same session_id", async ({
    authedPage: page,
    apiRequest,
  }) => {
    const customer = uniqueCustomerName("promote");
    const seed = await apiRequest.post("/api/enquiries", {
      data: { customer_name: customer, pax_count: 1 },
      failOnStatusCode: false,
    });
    expect([200, 201].includes(seed.status())).toBe(true);
    const id = ((await seed.json()) as { id: string }).id;

    // First promotion.
    await page.goto(`/app/enquiries/${id}`, { waitUntil: "domcontentloaded" });
    await Promise.all([
      page.waitForURL(/\/app\/chat\?session_id=/, { timeout: 15_000 }),
      page.getByRole("button", { name: /promote to chat session/i }).click(),
    ]);
    const firstUrl = new URL(page.url());
    const firstSessionId = firstUrl.searchParams.get("session_id");
    expect(firstSessionId).toBeTruthy();
    expect(firstSessionId!).toMatch(UUID_RE);

    // Second promotion. The button label flips to "Open chat session"
    // because the enquiry now has a session, but the action target is
    // unchanged.
    await page.goto(`/app/enquiries/${id}`, { waitUntil: "domcontentloaded" });
    await Promise.all([
      page.waitForURL(/\/app\/chat\?session_id=/, { timeout: 15_000 }),
      page.getByRole("button", { name: /open chat session/i }).click(),
    ]);
    const secondUrl = new URL(page.url());
    const secondSessionId = secondUrl.searchParams.get("session_id");
    expect(secondSessionId).toBe(firstSessionId);
  });
});
