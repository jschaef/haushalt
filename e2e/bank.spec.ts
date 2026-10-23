import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { login, png, tileValue, toast } from "./helpers";

test.use({ locale: "de-DE" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

const unique = (info: TestInfo, label: string) => `${label}-${info.project.name}-${Date.now()}`;

function ddmmyyyy(daysAgo = 0): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

function isoDate(daysAgo = 0): string {
  const [d, m, y] = ddmmyyyy(daysAgo).split(".");
  return `${y}-${m}-${d}`;
}

function csv(counterparty: string, amount: string, daysAgo = 0, purpose = "Bestellung") {
  return {
    name: "auszug.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(`Buchungstag;Empfänger;Verwendungszweck;Betrag\n${ddmmyyyy(daysAgo)};${counterparty};${purpose};${amount}\n`, "utf-8"),
  };
}

async function importFile(page: Page, file: { name: string; mimeType: string; buffer: Buffer }) {
  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(file);
}

const row = (page: Page, counterparty: string) => page.getByTestId("booking-row").filter({ hasText: counterparty });
const tab = (page: Page, name: RegExp | string) => page.getByRole("tab", { name });

test("import shows a summary; the same file again only reports duplicates", async ({ page }, info) => {
  const shop = unique(info, "Shop");
  const file = csv(shop, "-30,00");
  await importFile(page, file);
  await expect(toast(page, "success").filter({ hasText: "1 neu, 0 bereits vorhanden" })).toBeVisible();
  await expect(tab(page, /^Zu prüfen/)).toHaveAttribute("aria-selected", "true");
  await expect(row(page, shop)).toHaveCount(1);
  await expect(row(page, shop)).toContainText("30,00");

  await page.reload();
  await page.getByTestId("statement-input").setInputFiles(file);
  await expect(toast(page, "success").filter({ hasText: "0 neu, 1 bereits vorhanden" })).toBeVisible();
  await expect(row(page, shop)).toHaveCount(1);
});

test("deciding 'Zählt selbst' moves the booking to Gezählt and raises the dashboard total", async ({ page }, info) => {
  const shop = unique(info, "Zaehlt");
  await page.goto("/dashboard");
  await page.getByRole("tab", { name: "7 Tage", exact: true }).click();
  await expect(page.getByRole("tab", { name: "7 Tage", exact: true })).toHaveAttribute("aria-selected", "true");
  const before = await tileValue(page, "tile-total");

  await importFile(page, csv(shop, "-30,00", 0));
  const booking = row(page, shop);
  await expect(booking).toHaveCount(1);
  await booking.getByRole("button", { expanded: false }).click();
  await booking.getByLabel("Zählt selbst").selectOption({ label: "Haushalt" });
  await booking.getByRole("button", { name: "Zuordnen" }).last().click();
  await expect(toast(page, "success").filter({ hasText: "Buchung aktualisiert" })).toBeVisible();
  await expect(row(page, shop)).toHaveCount(0);

  await tab(page, "Gezählt").click();
  await expect(row(page, shop)).toContainText("Haushalt");

  await page.goto("/dashboard");
  await page.getByRole("tab", { name: "7 Tage", exact: true }).click();
  await expect(page.getByTestId("tile-total").locator("[data-value]").first()).toHaveAttribute("data-value", String(before + 3000));
});

test("a booking matching a confirmed receipt lands in Belege automatically", async ({ page }, info) => {
  const shop = unique(info, "Beleg");
  await page.goto("/receipts");
  await page.getByTestId("file-input").setInputFiles(png());
  await page.waitForURL(/\/receipts\/\d+$/);
  const id = Number(page.url().match(/\/receipts\/(\d+)$/)![1]);
  await page.locator("#store").fill(shop);
  await page.locator("#total").fill("47,11");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(toast(page, "success").filter({ hasText: "Gespeichert" })).toBeVisible();
  const confirm = page.getByRole("button", { name: /^Bestätigen$/ });
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await page.waitForURL(/\/receipts\?status=draft/);

  await importFile(page, csv(shop, "-47,11", 0, "Kartenzahlung"));
  await expect(toast(page, "success").filter({ hasText: "1 zu Belegen" })).toBeVisible();
  await expect(row(page, shop)).toHaveCount(0);
  await tab(page, "Belege").click();
  const booking = row(page, shop);
  await expect(booking).toHaveCount(1);
  await expect(booking.getByRole("link", { name: "Beleg ansehen" })).toHaveAttribute("href", `/receipts/${id}`);
});

test("ignore a booking and send it back to review", async ({ page }, info) => {
  const shop = unique(info, "Ignorieren");
  await importFile(page, csv(shop, "-12,00"));
  const booking = row(page, shop);
  await expect(booking).toHaveCount(1);
  await booking.getByRole("button", { expanded: false }).click();
  await booking.getByRole("button", { name: "Ignorieren" }).click();
  await expect(row(page, shop)).toHaveCount(0);

  await tab(page, "Ignoriert").click();
  await expect(row(page, shop)).toHaveCount(1);
  await row(page, shop).getByRole("button", { expanded: false }).click();
  await row(page, shop).getByRole("button", { name: "Zurück zur Prüfung" }).click();
  await expect(row(page, shop)).toHaveCount(0);

  await tab(page, /^Zu prüfen/).click();
  await expect(row(page, shop)).toHaveCount(1);
});

test("a CAMT XML statement can be imported", async ({ page }, info) => {
  const shop = unique(info, "Camt");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt><Ntry><Amt Ccy="EUR">19.99</Amt><CdtDbtInd>DBIT</CdtDbtInd>
<Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>${isoDate(0)}</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Cdtr><Pty><Nm>${shop}</Nm></Pty></Cdtr><CdtrAcct><Id><IBAN>DE11</IBAN></Id></CdtrAcct></RltdPties>
<RmtInf><Ustrd>Rechnung</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry></Stmt></BkToCstmrStmt></Document>`;
  await importFile(page, { name: "auszug.xml", mimeType: "application/xml", buffer: Buffer.from(xml, "utf-8") });
  await expect(toast(page, "success").filter({ hasText: "1 neu" })).toBeVisible();
  await expect(row(page, shop)).toContainText("19,99");
});
