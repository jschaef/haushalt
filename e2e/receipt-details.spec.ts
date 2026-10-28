import { expect, test } from "@playwright/test";
import { login, png, toast, uploadOne } from "./helpers";

test.use({ locale: "de-DE" });

// the fake reader takes a "printed" TSE transaction from bytes after the image
function withTse(number: string) {
  const file = png();
  return { ...file, buffer: Buffer.concat([file.buffer, Buffer.from(`fake-tse:${number}`)]) };
}

test("a discount belongs to its article; a receipt read twice is not stored again", async ({ page }, info) => {
  await login(page);
  const tse = `${info.project.name}${Date.now()}`;
  const id = await uploadOne(page, withTse(tse));

  // time, receipt number and TSE as printed
  await expect(page.locator("#time")).toHaveValue("18:05");
  await expect(page.locator("#receipt-number")).toHaveValue("4711");
  await expect(page.getByTestId("tse")).toContainText(tse);

  // "Preisvorteil" under the bananas: printed 2,29, discount 0,30, paid 1,99
  const bananas = page.getByTestId("items").locator("li").filter({ has: page.locator('input[value="Bio Bananen"]') });
  await expect(bananas.getByLabel("Betrag")).toHaveValue("2,29");
  const discount = bananas.getByTestId("discount");
  await expect(discount).toContainText("Preisvorteil");
  await expect(discount).toContainText("bezahlt 1,99");
  await expect(page.getByTestId("mismatch")).toHaveCount(0);

  // a bigger discount changes what was paid and is stored
  await bananas.getByLabel("Rabatt für Bio Bananen").fill("0,50");
  await expect(discount).toContainText("bezahlt 1,79");
  await page.locator("#total").fill("12,23");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(toast(page, "success").filter({ hasText: "Gespeichert" })).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("items").getByLabel("Rabatt für Bio Bananen")).toHaveValue("0,50");

  // the same receipt again: no second receipt, the existing one opens
  await page.goto("/receipts");
  await page.getByTestId("file-input").setInputFiles(withTse(tse));
  await expect(page.getByText("1 Beleg(e) schon erfasst")).toBeVisible();
  await page.waitForURL(new RegExp(`/receipts/${id}$`));
});
