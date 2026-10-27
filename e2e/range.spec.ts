import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

function iso(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

test("a custom period with start and optional end is remembered", async ({ page }) => {
  await login(page);
  await page.goto("/dashboard");
  await page.getByRole("tab", { name: "Eigener Zeitraum" }).click();
  const fields = page.getByTestId("custom-range");
  await fields.getByLabel("Von").fill(iso(9));
  // no end: up to today
  await expect(page.getByText("· 10 Tage")).toBeVisible();
  await fields.getByLabel("Bis (optional)").fill(iso(5));
  await expect(page.getByText("· 5 Tage")).toBeVisible();

  // the browser remembers the choice
  await page.reload();
  await expect(page.getByRole("tab", { name: "Eigener Zeitraum" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("custom-range").getByLabel("Von")).toHaveValue(iso(9));
  await expect(page.getByText("· 5 Tage")).toBeVisible();
  await page.getByRole("tab", { name: "30 Tage" }).click();
  await expect(page.getByTestId("custom-range")).toHaveCount(0);
});

test("an impossible period asks for a valid one instead of loading forever", async ({ page }) => {
  await login(page);
  await page.goto("/dashboard");
  await page.getByRole("tab", { name: "Eigener Zeitraum" }).click();
  const fields = page.getByTestId("custom-range");
  await fields.getByLabel("Von").fill(iso(3));
  await fields.getByLabel("Bis (optional)").fill(iso(6));
  await expect(page.getByTestId("range-incomplete")).toBeVisible();
  await fields.getByLabel("Bis (optional)").fill("");
  await expect(page.getByText("· 4 Tage")).toBeVisible();
});
