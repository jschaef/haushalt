import { expect, test } from "@playwright/test";
import { createConfirmedReceipt, login } from "./helpers";

test.use({ locale: "de-DE" });

test("purchases list food and non-food products with quantities, search and filters", async ({ page }) => {
  await login(page);
  await createConfirmedReceipt(page);

  await page.goto("/purchases");
  await expect(page.getByRole("heading", { name: "Einkäufe" })).toBeVisible();
  await expect(page.getByTestId("purchases-food")).toContainText("€");
  const products = page.getByTestId("product-row");
  // the fake receipt: bananas weighed in kg, washing-up liquid is non-food
  const bananas = products.filter({ hasText: "Bio Bananen" });
  await expect(bananas).toContainText("kg");
  await expect(bananas).toContainText("REWE");

  await page.getByLabel("Art").selectOption({ label: "Nicht-Lebensmittel" });
  await expect(products.filter({ hasText: "Spülmittel" })).toBeVisible();
  await expect(products.filter({ hasText: "Bio Bananen" })).toHaveCount(0);

  await page.getByLabel("Art").selectOption({ label: "Alle" });
  await page.getByLabel("Produkt suchen").fill("banane");
  await expect(products.filter({ hasText: "Spülmittel" })).toHaveCount(0);
  await expect(bananas).toBeVisible();

  await page.getByLabel("Geschäft").selectOption({ label: "REWE" });
  await bananas.getByRole("button").click();
  const lines = bananas.getByTestId("product-lines");
  await expect(lines).toContainText("REWE");
  await expect(lines.getByRole("link").first()).toHaveAttribute("href", /\/receipts\/\d+$/);
});

test("the receipts page links to the purchases, categories say what is food", async ({ page }) => {
  await login(page);
  await page.goto("/receipts");
  await page.getByTestId("purchases-link").click();
  await expect(page).toHaveURL(/\/purchases$/);

  await page.goto("/settings");
  const groceries = page.getByTestId("category-row").filter({ hasText: "Lebensmittel" }).first();
  await expect(groceries.getByText("Lebensmittel", { exact: true }).last()).toBeVisible();
});
