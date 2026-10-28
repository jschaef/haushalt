import { expect, test } from "@playwright/test";
import { login, png, toast, uploadOne } from "./helpers";

test.use({ locale: "de-DE" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("single upload opens the editor; edit, save, confirm, list under Bestätigt", async ({ page }) => {
  const id = await uploadOne(page);

  await expect(page.locator("#store")).toHaveValue("REWE");
  await expect(page.getByTestId("items").locator("li")).toHaveCount(5);
  await expect(page.locator("#total")).toHaveValue(/^12,43/);

  const firstCategory = page.getByTestId("items").locator("li").first().getByRole("combobox", { name: "Kategorie" });
  await firstCategory.selectOption({ label: "Haushalt" });
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(toast(page, "success").filter({ hasText: "Gespeichert" })).toBeVisible();

  // the change was stored: reload and read it back
  await page.reload();
  await expect(page.getByTestId("items").locator("li").first().getByRole("combobox", { name: "Kategorie" })).toHaveValue(
    await page.getByTestId("items").locator("li").first().getByRole("combobox", { name: "Kategorie" }).locator("option", { hasText: "Haushalt" }).getAttribute("value") as string,
  );

  await page.getByRole("button", { name: "Bestätigen" }).click();
  await page.waitForURL(/\/receipts\?status=draft/);
  await expect(toast(page, "success").filter({ hasText: "Beleg bestätigt" })).toBeVisible();

  // not a draft any more
  await expect(page.locator(`a[href="/receipts/${id}"]`)).toHaveCount(0);
  await page.getByRole("tab", { name: "Bestätigt" }).click();
  const row = page.locator(`a[href="/receipts/${id}"]`);
  await expect(row).toBeVisible();
  await expect(row).toContainText("REWE");
  await expect(row).toContainText("12,43");
});

test("bulk upload lists drafts; delete one via the editor", async ({ page }) => {
  await page.goto("/receipts?status=draft");
  const rows = page.getByTestId("receipt-row");
  await expect(page.getByRole("tab", { name: "Zu prüfen" })).toHaveAttribute("aria-selected", "true");
  await expect(rows.first().or(page.getByText("Keine Belege"))).toBeVisible();
  const before = await rows.count();

  await page.getByTestId("file-input").setInputFiles([png("a.png"), png("b.png")]);
  await expect(toast(page, "success").filter({ hasText: "2 Beleg(e) gelesen" })).toBeVisible();
  await expect(rows).toHaveCount(before + 2);
  await expect(rows.filter({ hasText: "REWE" }).filter({ hasText: "Entwurf" }).first()).toBeVisible();

  const hrefs = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("href")!));
  const target = hrefs[0];
  await rows.first().click();
  await page.waitForURL(`**${target}`);
  await expect(page.locator("#store")).toHaveValue("REWE");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Löschen" }).filter({ hasText: "Löschen" }).click();
  await page.waitForURL(/\/receipts$/);
  await page.getByRole("tab", { name: "Zu prüfen" }).click();
  await expect(page.locator(`a[href="${target}"]`)).toHaveCount(0);
  await expect(rows).toHaveCount(before + 1);
});

test("a non-receipt file shows an error and creates nothing", async ({ page }) => {
  await page.goto("/receipts");
  const rows = page.getByTestId("receipt-row");
  await expect(rows.first().or(page.getByText("Keine Belege"))).toBeVisible();
  const before = await rows.count();

  await page.getByTestId("file-input").setInputFiles({ name: "a.png", mimeType: "image/png", buffer: Buffer.from("hello") });
  await expect(toast(page, "error")).toBeVisible();
  await expect(page).toHaveURL(/\/receipts$/);

  await page.reload();
  await expect(rows.first().or(page.getByText("Keine Belege"))).toBeVisible();
  await expect(rows).toHaveCount(before);
});
