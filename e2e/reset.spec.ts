import { expect, test } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

test("an admin starts the dashboard anew from a reset date and lifts it again", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  const tile = page.getByTestId("reset-tile");
  await expect(tile.getByTestId("reset-state")).toHaveText("Das Dashboard zählt alle Daten.");
  try {
    // the field starts at today
    await tile.getByRole("button", { name: "Ab diesem Tag zählen" }).click();
    await expect(toast(page, "success").filter({ hasText: "zählt ab dem Stichtag" })).toBeVisible();
    await expect(tile.getByTestId("reset-state")).toContainText("Das Dashboard zählt ab");

    await page.goto("/dashboard");
    await expect(page.getByTestId("dash-since")).toContainText("Neu gezählt ab");
    await expect(page.getByText("· 1 Tage")).toBeVisible();
  } finally {
    // the other tests share this database
    await page.goto("/settings");
    await page.getByTestId("reset-tile").getByRole("button", { name: "Stichtag aufheben" }).click();
    await expect(toast(page, "success").filter({ hasText: "Stichtag aufgehoben" })).toBeVisible();
  }
  await page.goto("/dashboard");
  await expect(page.getByTestId("dash-since")).toHaveCount(0);
});
