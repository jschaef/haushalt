import { expect, test } from "@playwright/test";
import { login, tileValue, toast } from "./helpers";

test.use({ locale: "de-DE" });

test("monthly fixed cost shows per-day amount, raises the daily average, can be deleted", async ({ page }) => {
  await login(page);
  const before = await tileValue(page, "tile-daily");

  await page.goto("/fixed");
  await page.getByLabel("Bezeichnung").fill("Strom Abschlag");
  await page.getByLabel("Betrag").fill("60,00");
  await page.getByLabel("Kategorie").selectOption({ label: "Strom" });
  await page.getByLabel("Turnus").selectOption({ label: "monatlich" });
  await page.getByRole("button", { name: "Hinzufügen" }).click();
  await expect(toast(page, "success")).toBeVisible();

  const row = page.getByTestId("recurring-row").filter({ hasText: "Strom Abschlag" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("60,00");
  await expect(row).toContainText("Strom");
  await expect(row).toContainText(/\d+,\d{2}\s*€ pro Tag/);

  await page.goto("/dashboard");
  await expect(page.getByTestId("tile-daily").locator("[data-value]").first()).not.toHaveAttribute("data-value", String(before));
  expect(await tileValue(page, "tile-daily")).toBeGreaterThan(before);

  await page.goto("/fixed");
  const again = page.getByTestId("recurring-row").filter({ hasText: "Strom Abschlag" });
  await expect(again).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await again.getByRole("button", { name: "Löschen" }).click();
  await expect(page.getByTestId("recurring-row").filter({ hasText: "Strom Abschlag" })).toHaveCount(0);

  await page.goto("/dashboard");
  await expect.poll(() => tileValue(page, "tile-daily")).toBe(before);
});
