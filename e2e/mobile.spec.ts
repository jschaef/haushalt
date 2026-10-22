import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

test("bottom tab bar is visible on phones and navigates to Belege", async ({ page, isMobile }) => {
  test.skip(!isMobile, "tab bar exists on phones only");
  await login(page);
  const tabs = page.getByRole("navigation", { name: "Main" });
  await expect(tabs).toBeVisible();
  await tabs.getByRole("link", { name: "Belege" }).click();
  await page.waitForURL("**/receipts");
  await expect(page.getByRole("heading", { name: "Belege" })).toBeVisible();
  await tabs.getByRole("link", { name: "Nebenkosten" }).click();
  await page.waitForURL("**/utilities");
  // fixed costs are not in the tab bar; the utilities page links to them
  await expect(tabs.getByRole("link", { name: "Fixkosten" })).toHaveCount(0);
  await page.locator('main a[href="/fixed"]').filter({ visible: true }).first().click();
  await page.waitForURL("**/fixed");
});

test("desktop has no bottom tab bar", async ({ page, isMobile }) => {
  test.skip(!!isMobile, "desktop only");
  await login(page);
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
});
