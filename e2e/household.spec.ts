import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

test("the settings name the household; its admin can rename it", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  const tile = page.getByTestId("household-tile");
  await expect(tile.getByLabel("Name des Haushalts")).toHaveValue(/.+/);
  await expect(tile).toContainText("Andere Haushalte sehen sie nicht.");
});
