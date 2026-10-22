import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

test("language toggle switches DE/EN and persists after reload", async ({ page, context }) => {
  await login(page);
  // the visible nav link (header on desktop, tab bar on phones)
  const receipts = () => page.locator('a[href="/receipts"]:not([aria-label])').filter({ visible: true });
  const fixed = () => page.locator('a[href="/fixed"]').filter({ visible: true });
  await expect(receipts()).toHaveText("Belege");
  await expect(fixed()).toHaveText("Fixkosten");

  await page.getByTestId("language-toggle").click();
  await expect(receipts()).toHaveText("Receipts");
  await expect(fixed()).toHaveText("Fixed costs");
  await expect.poll(async () => (await context.cookies()).find((c) => c.name === "haushalt_locale")?.value).toBe("en");

  await page.reload();
  await expect(receipts()).toHaveText("Receipts");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  await page.getByTestId("language-toggle").click();
  await expect(receipts()).toHaveText("Belege");
  await page.reload();
  await expect(receipts()).toHaveText("Belege");
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
});
