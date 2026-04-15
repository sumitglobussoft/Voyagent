// i18n locale-switch flow.
//
// Sign in as a fresh tenant, flip the locale switcher to Hindi, and
// assert that:
//   1. The switcher itself shows Hindi text (the hard-coded "भाषा" label
//      proves the LocaleProvider re-rendered against the Hindi dict).
//   2. The `voyagent_locale` cookie is set to "hi".
//   3. After a full reload the Hindi label persists (cookie survives).
//   4. Switching back to English reverts the dictionary.
//
// AppSidebar text is not asserted because its labels are hard-coded
// strings in a component outside this wave's scope — the cookie +
// LocaleSwitcher assertions cover the contract we actually own.

import { test, expect } from "../fixtures/authed";

test.describe("i18n", () => {
  test("locale switch persists via cookie and re-renders", async ({
    authedPage,
  }) => {
    const page = authedPage;

    await page.goto("/app/settings", { waitUntil: "domcontentloaded" });

    const switcher = page.getByTestId("locale-switcher");
    await expect(switcher).toBeVisible({ timeout: 10_000 });

    // Default locale is English.
    await expect(switcher).toContainText(/language/i);

    // Flip to Hindi.
    const select = switcher.locator("select");
    await select.selectOption("hi");
    // The provider reloads the page after writing the cookie; wait for
    // the reload to settle on the same URL.
    await page.waitForLoadState("domcontentloaded");
    await expect(page).toHaveURL(/\/app\/settings/);

    // Cookie persisted.
    const cookies = await page.context().cookies();
    const locale = cookies.find((c) => c.name === "voyagent_locale");
    expect(locale?.value).toBe("hi");

    // After reload the dictionary is Hindi — the switcher label is
    // "भाषा" and the select itself reports value="hi".
    const switcherAfter = page.getByTestId("locale-switcher");
    await expect(switcherAfter).toBeVisible();
    await expect(switcherAfter).toContainText("भाषा");
    await expect(switcherAfter.locator("select")).toHaveValue("hi");

    // Hard reload — Hindi still persists via cookie.
    await page.reload({ waitUntil: "domcontentloaded" });
    const switcherReloaded = page.getByTestId("locale-switcher");
    await expect(switcherReloaded).toContainText("भाषा");
    await expect(switcherReloaded.locator("select")).toHaveValue("hi");

    // Back to English.
    await switcherReloaded.locator("select").selectOption("en");
    await page.waitForLoadState("domcontentloaded");
    const switcherEn = page.getByTestId("locale-switcher");
    await expect(switcherEn).toContainText(/language/i);
    await expect(switcherEn.locator("select")).toHaveValue("en");
  });
});
