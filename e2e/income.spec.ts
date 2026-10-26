import { expect, test, type Page } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

function today(): string {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

function statement(rows: [string, string, string][]) {
  const lines = ["Buchungstag;Empfänger;Verwendungszweck;Betrag", ...rows.map(([who, why, amount]) => `${today()};${who};${why};${amount}`)];
  return { name: "umsaetze.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

async function income(page: Page): Promise<number> {
  return page.evaluate(async () => (await (await fetch("/api/v1/stats/summary?range=30d")).json()).income_cents as number);
}

test("incoming salary is income and shows against spending on the dashboard", async ({ page }, info) => {
  const payer = `Arbeitgeber ${info.project.name} ${Date.now()}`;
  await login(page);
  const before = await income(page);

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(statement([[payer, "Gehalt", "1234,56"]]));
  await expect(toast(page, "success")).toBeVisible();
  const row = page.getByTestId("booking-row").filter({ hasText: payer });
  await row.getByRole("button", { expanded: false }).click();
  // money coming in: no receipt or fixed cost, an income category or a refund
  await expect(row.getByText("Gehört zu Beleg")).toHaveCount(0);
  await row.getByLabel("Einnahme oder Erstattung").selectOption({ label: "Gehalt & Lohn" });
  await row.getByRole("button", { name: "Zuordnen" }).last().click();
  await expect(toast(page, "success").filter({ hasText: "Buchung aktualisiert" })).toBeVisible();
  expect(await income(page)).toBe(before + 123456);

  await page.goto("/dashboard");
  const tile = page.getByTestId("tile-cashflow");
  await expect(tile).toContainText("Einnahmen und Ausgaben");
  await expect(tile.getByTestId("cash-income")).not.toHaveText("0,00 €");
  await expect(tile.getByTestId("cash-balance")).toBeVisible();
});

// made-up IBANs with valid check digits, one pair per browser project
const SAVINGS: Record<string, { giro: string; savings: string }> = {
  desktop: { giro: "DE37100200300000007777", savings: "DE13100200300000008888" },
  phone: { giro: "DE11100200300000009991", savings: "DE81100200300000009992" },
};

function giroStatement(own: string, rows: [string, string, string, string][]) {
  const lines = [
    "Umsätze",
    "Konto;Filial-/Kontonummer;IBAN;Währung",
    `Giro;000 0000000 00;${own};EUR`,
    "",
    "Buchungstag;Wert;Umsatzart;Begünstigter / Auftraggeber;Verwendungszweck;IBAN / Kontonummer;BIC;Kundenreferenz;" +
      "Mandatsreferenz;Gläubiger ID;Fremde Gebühren;Betrag;Abweichender Empfänger;Anzahl der Aufträge;Anzahl der Schecks;Soll;Haben;Währung",
    ...rows.map(([who, why, iban, amount]) => `${today()};${today()};Überweisung;${who};${why};${iban};;;;;;${amount};;;;;;EUR`),
  ];
  return { name: "giro.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

test("a transfer to a savings account shows as saved", async ({ page }, info) => {
  const { giro, savings } = SAVINGS[info.project.name];
  await login(page);
  const before = await page.evaluate(async () => (await (await fetch("/api/v1/stats/summary?range=30d")).json()).saved_cents as number);

  await page.goto("/settings");
  const tile = page.getByTestId("accounts-tile");
  await tile.getByLabel("Name").last().fill(`Tagesgeld ${info.project.name}`);
  await tile.getByLabel("Art").last().selectOption("savings");
  await tile.getByLabel("IBAN").last().fill(savings);
  await tile.getByRole("button", { name: "Konto hinzufügen" }).click();
  await expect(tile.getByTestId("account-row").filter({ has: page.locator(`input[value="${savings}"]`) })).toBeVisible();

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(giroStatement(giro, [["Ich", "Sparen", savings, "-77,77"]]));
  await expect(toast(page, "success").filter({ hasText: "1 Umbuchung" })).toBeVisible();

  const after = await page.evaluate(async () => (await (await fetch("/api/v1/stats/summary?range=30d")).json()).saved_cents as number);
  expect(after).toBe(before + 7777);
  await page.goto("/dashboard");
  await expect(page.getByTestId("cash-saved")).toBeVisible();
});

test("a large booking is suggested as one-off and then counts apart", async ({ page }, info) => {
  const payer = `Tante ${info.project.name} ${Date.now()}`;
  await login(page);
  const oneOff = async () =>
    page.evaluate(async () => (await (await fetch("/api/v1/stats/summary?range=30d")).json()).one_off.in_cents as number);
  const before = await oneOff();

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(statement([[payer, "Geschenk", "5000,00"]]));
  await expect(toast(page, "success")).toBeVisible();
  const row = page.getByTestId("booking-row").filter({ hasText: payer });
  // above the default threshold (1.000 €): suggested, never marked by the app
  await expect(row.getByTestId("one-off-badge")).toHaveCount(0);
  await row.getByTestId("one-off-suggestion").getByRole("button", { name: "Als einmalig markieren" }).click();
  await expect(toast(page, "success").filter({ hasText: "Als einmalig markiert" })).toBeVisible();
  await expect(row.getByTestId("one-off-badge")).toBeVisible();
  await expect(row.getByTestId("one-off-suggestion")).toHaveCount(0);
  expect(await oneOff()).toBe(before + 500000);

  await page.goto("/dashboard");
  await expect(page.getByTestId("cash-one-off")).toContainText("Einmalig");

  await page.goto("/settings");
  await expect(page.getByTestId("one-off-tile").getByLabel("Vorschlag ab Betrag (€)")).toHaveValue("1000");
});
