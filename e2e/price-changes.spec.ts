import { expect, test, type Page } from "@playwright/test";
import { PNG, login } from "./helpers";

test.use({ locale: "de-DE" });

function isoDay(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** A confirmed receipt with one article, through the API (same origin). */
async function buy(page: Page, origin: string, store: string, name: string, cents: number, daysAgo: number) {
  const headers = { Origin: origin };
  const upload = await page.request.post("/api/v1/receipts", {
    headers,
    multipart: { files: { name: "bon.png", mimeType: "image/png", buffer: Buffer.concat([PNG, Buffer.from(`${name}${cents}${daysAgo}`)]) } },
  });
  expect(upload.status()).toBe(201);
  const [receipt] = await upload.json();
  const patched = await page.request.patch(`/api/v1/receipts/${receipt.id}`, {
    headers,
    data: {
      store_name: store,
      purchased_on: isoDay(daysAgo),
      total_cents: cents,
      items: [{ name, quantity: 1, unit: "piece", total_cents: cents, category_id: receipt.items[0].category_id }],
    },
  });
  expect(patched.status()).toBe(200);
  expect((await page.request.post(`/api/v1/receipts/${receipt.id}/confirm`, { headers })).status()).toBe(200);
}

test("price changes of the same article in the same store, with history and filters", async ({ page, baseURL }, info) => {
  await login(page);
  // own names: other specs share the database of the run
  const tag = `${info.project.name}${Date.now()}`;
  const article = `Preistest ${tag} 1L`;
  const store = `Laden ${tag}`;
  await buy(page, baseURL!, store, article, 100, 10);
  await buy(page, baseURL!, store, article, 125, 2);
  // the same article elsewhere is no price change
  await buy(page, baseURL!, `Anderswo ${tag}`, article, 300, 1);

  await page.goto("/purchases");
  await page.getByRole("tab", { name: "Preisänderungen" }).click();
  await expect(page.getByRole("tab", { name: "Preisänderungen" })).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("Produkt suchen").fill(tag);
  const rows = page.getByTestId("price-row");
  await expect(rows).toHaveCount(1);
  const row = rows.first();
  await expect(row).toContainText(store);
  await expect(row).toContainText("1,25 €/Stück");
  await expect(row).toContainText("+0,25 €");
  await expect(row).toContainText("+25 %");
  await expect(row).toContainText("vorher 1,00 €/Stück");

  await row.getByRole("button").click();
  const history = row.getByTestId("price-history");
  await expect(history.getByRole("listitem")).toHaveCount(2);
  await expect(history.getByRole("link").first()).toHaveAttribute("href", /\/receipts\/\d+$/);

  await page.getByLabel("Richtung").selectOption({ label: "billiger" });
  await expect(rows).toHaveCount(0);
  await expect(page.getByText(/Keine Preisänderungen/)).toBeVisible();
  await page.getByLabel("Richtung").selectOption({ label: "teurer" });
  await page.getByLabel("Mindestens (%)").fill("30");
  await expect(rows).toHaveCount(0);
  await page.getByLabel("Mindestens (%)").fill("20");
  await expect(rows).toHaveCount(1);

  // back to the products
  await page.getByRole("tab", { name: "Produkte" }).click();
  await expect(page.getByTestId("purchases-filters")).toBeVisible();
});
