import { expect, test, type Page } from "@playwright/test";
import { PNG, login, uploadOne } from "./helpers";

test.use({ locale: "de-DE" });

/** A confirmed receipt with one article through the API; compare_name undefined = not named yet. */
async function buy(page: Page, origin: string, store: string, name: string, cents: number, compare_name?: string) {
  const headers = { Origin: origin };
  const upload = await page.request.post("/api/v1/receipts", {
    headers,
    multipart: { files: { name: "bon.png", mimeType: "image/png", buffer: Buffer.concat([PNG, Buffer.from(`${store}${name}${cents}`)]) } },
  });
  expect(upload.status()).toBe(201);
  const [receipt] = await upload.json();
  const item = { name, quantity: 1, unit: "piece", total_cents: cents, category_id: receipt.items[0].category_id, ...(compare_name !== undefined && { compare_name }) };
  const patched = await page.request.patch(`/api/v1/receipts/${receipt.id}`, {
    headers,
    data: { store_name: store, purchased_on: new Date().toISOString().slice(0, 10), total_cents: cents, items: [item] },
  });
  expect(patched.status()).toBe(200);
  expect((await page.request.post(`/api/v1/receipts/${receipt.id}/confirm`, { headers })).status()).toBe(200);
}

test("the same product across stores, cheapest first; older lines get names on request", async ({ page, baseURL }, info) => {
  await login(page);
  // own names: other specs share the database of the run
  const tag = `${info.project.name}${Date.now()}`;
  const product = `Vergleichsmilch ${tag} 1 l`;
  await buy(page, baseURL!, `Teuer ${tag}`, `JA! Milch ${tag}`, 129, product);
  await buy(page, baseURL!, `Billig ${tag}`, `Milbona Milch ${tag}`, 99, product);
  // read before comparison names existed: the fake namer drops the brand words
  await buy(page, baseURL!, `Teuer ${tag}`, `JA! Quark ${tag}`, 79);
  await buy(page, baseURL!, `Billig ${tag}`, `Milbona Quark ${tag}`, 69);

  await page.goto("/purchases");
  await page.getByRole("tab", { name: "Supermarktvergleich" }).click();
  await page.getByLabel("Produkt suchen").fill(tag);
  const rows = page.getByTestId("compare-row");
  const milk = rows.filter({ hasText: product });
  await expect(milk).toBeVisible();
  const stores = milk.getByTestId("compare-store");
  await expect(stores.first()).toContainText(`Billig ${tag}`);
  await expect(stores.first()).toContainText("am günstigsten");
  await expect(stores.first()).toContainText("0,99 €/Stück");
  await expect(stores.nth(1)).toContainText("1,29 €/Stück");
  await expect(milk).toContainText("0,30 € (30,3 %) Unterschied");
  await expect(milk).toContainText(`auf dem Bon: Milbona Milch ${tag}`);
  await expect(rows.filter({ hasText: "Quark" })).toHaveCount(0);

  await page.getByRole("button", { name: "Vergleichsnamen vergeben" }).click();
  await expect(rows.filter({ hasText: `Quark ${tag}` })).toBeVisible();
  await expect(page.getByTestId("compare-unnamed")).toHaveCount(0);
});

test("the receipt editor shows and keeps the comparison name", async ({ page }) => {
  await login(page);
  await uploadOne(page);
  const names = page.getByTestId("compare-name");
  await expect(names.first()).toHaveValue("Vollmilch 3,5 % 1 l");
  await names.first().fill("Milch 3,5 % 1 l");
  await page.getByRole("button", { name: /^(Speichern|Save)$/ }).click();
  await page.reload();
  await expect(page.getByTestId("compare-name").first()).toHaveValue("Milch 3,5 % 1 l");
});
