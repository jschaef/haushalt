import { expect, test } from "@playwright/test";
import { createConfirmedReceipt, login, tileValue } from "./helpers";

test.use({ locale: "de-DE" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("confirming a receipt raises the total by its amount", async ({ page }) => {
  await page.goto("/dashboard");
  const before = await tileValue(page, "tile-total");

  await createConfirmedReceipt(page);

  await page.goto("/dashboard");
  await expect(page.getByTestId("tile-total").locator("[data-value]").first()).toHaveAttribute("data-value", String(before + 1243));
});

test("range tabs switch and the average tiles are present", async ({ page }) => {
  await page.goto("/dashboard");
  for (const id of ["tile-daily", "tile-week", "tile-month", "tile-year", "tile-total", "tile-review"]) {
    await expect(page.getByTestId(id)).toBeVisible();
  }
  await expect(page.getByTestId("tile-daily").locator("[data-value]").first()).toHaveAttribute("data-value", /^\d+$/);

  await expect(page.getByRole("tab", { name: "30 Tage" })).toHaveAttribute("aria-selected", "true");
  for (const name of ["7 Tage", "90 Tage", "12 Monate", "Gesamt"]) {
    const tab = page.getByRole("tab", { name, exact: true });
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("tile-total")).toBeVisible();
    await expect(page.getByTestId("tile-daily").locator("[data-value]").first()).toHaveAttribute("data-value", /^\d+$/);
  }
  // "Gesamt" covers at least what 7 days cover
  const all = await tileValue(page, "tile-total");
  await page.getByRole("tab", { name: "7 Tage", exact: true }).click();
  await expect(page.getByRole("tab", { name: "7 Tage", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect.poll(async () => tileValue(page, "tile-total")).toBeLessThanOrEqual(all);
});
