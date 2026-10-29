import { expect, test } from "@playwright/test";
import { createConfirmedReceipt, login } from "./helpers";

test.use({ locale: "de-DE" });

test("the report filters with OR within a field, NOT and AND, sums, groups and exports", async ({ page }) => {
  await login(page);
  const id = await createConfirmedReceipt(page);

  await page.goto("/report");
  await expect(page.getByRole("heading", { name: "Auswertung", level: 1 })).toBeVisible();
  await expect(page.getByTestId("report-spending")).toContainText("€");
  const entries = page.getByTestId("report-entry");
  // other specs add receipts too: only the lines of this one
  const own = entries.filter({ has: page.locator(`a[href="/receipts/${id}"]`) });
  const water = own.filter({ hasText: "Mineralwasser" });
  const soap = own.filter({ hasText: "Spülmittel" });

  // AND: text and categories; OR: two categories
  await page.getByLabel("Text enthält").fill("Mineralwasser");
  await expect(water).toBeVisible();
  await expect(water).toContainText("REWE");
  const categories = page.getByTestId("choice-categories");
  await categories.locator("summary").click();
  await categories.getByLabel("Lebensmittel", { exact: true }).check();
  await categories.getByLabel("Getränke", { exact: true }).check();
  await expect(categories.locator("summary")).toContainText("2 gewählt");
  await expect(water).toBeVisible();
  // NOT: neither groceries nor drinks
  await categories.getByLabel("ausschließen (NICHT)").check();
  await expect(categories.locator("summary")).toContainText("ohne 2");
  await expect(water).toHaveCount(0);

  await page.getByLabel("Text enthält").fill("Spülmittel");
  await expect(soap).toBeVisible();
  // text NOT
  await page.getByLabel("Text ausschließen").check();
  await expect(soap).toHaveCount(0);

  // reset keeps the period, groups by store
  await page.getByTestId("report-reset").click();
  await expect(page.getByLabel("Text enthält")).toHaveValue("");
  await expect(page.getByTestId("report-reset")).toHaveCount(0);
  await page.getByLabel("Gruppieren nach").selectOption({ label: "Geschäft / Empfänger" });
  // other specs add payees like "REWE Markt GmbH": the exact store name
  await expect(page.getByTestId("report-group").filter({ has: page.getByText("REWE", { exact: true }) })).toBeVisible();

  // sources and amounts
  await page.getByRole("checkbox", { name: "Beleg", exact: true }).check();
  await page.getByLabel("Betrag ab (€)").fill("3,50");
  await page.getByLabel("Betrag bis (€)").fill("3,60");
  await expect(water).toBeVisible();
  await expect(soap).toHaveCount(0);
  await page.getByLabel("Betrag bis (€)").fill("abc");
  await expect(page.getByText("Kein gültiger Betrag")).toBeVisible();
  await page.getByLabel("Betrag bis (€)").fill("");

  // the CSV holds the selected entries
  const link = page.getByTestId("report-csv");
  await expect(link).toHaveAttribute("href", /report\/csv\?.*source=receipt.*min_cents=350/);
  const csv = await page.request.get((await link.getAttribute("href"))!);
  expect(csv.status()).toBe(200);
  expect(csv.headers()["content-type"]).toContain("text/csv");
  const text = await csv.text();
  expect(text).toContain("Datum;bis;Quelle;Text");
  expect(text).toContain("Mineralwasser");
  expect(text).not.toContain("Spülmittel");

  await water.getByRole("link").click();
  await expect(page).toHaveURL(/\/receipts\/\d+$/);
});

test("the dashboard links to the report", async ({ page }) => {
  await login(page);
  await page.getByTestId("report-link").click();
  await expect(page).toHaveURL(/\/report$/);
  await expect(page.getByRole("heading", { name: "Auswertung", level: 1 })).toBeVisible();
});
