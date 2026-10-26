import { expect, test } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

// made up, one card, giro IBAN and statement total per browser project
const DATA: Record<string, { card: string; giro: string; amounts: [string, string]; total: string }> = {
  desktop: { card: "4000********1111", giro: "DE85100200300000005555", amounts: ["-12,34", "-0,25"], total: "-12,59" },
  phone: { card: "4000********2222", giro: "DE61100200300000006666", amounts: ["-23,45", "-0,47"], total: "-23,92" },
};

function today(leadingZeros = true): string {
  const d = new Date();
  const day = leadingZeros ? String(d.getDate()).padStart(2, "0") : String(d.getDate());
  const month = leadingZeros ? String(d.getMonth() + 1).padStart(2, "0") : String(d.getMonth() + 1);
  return `${day}.${month}.${d.getFullYear()}`;
}

// layout of a German card export: card above the table, euro amount after the rate
function cardCsv(card: string, shop: string, [purchase, fee]: [string, string]) {
  const lines = [
    "Kreditkartentransaktionen",
    "Kreditkarte;Kundennummer;Kartennummer;Karteninhaber",
    `Visa Card (Kreditkarte);000 0000000;${card};MAX MUSTER`,
    "",
    `Abrechnungsdatum: ${today(false)}`,
    "Belegdatum;Eingangstag;Verwendungszweck;Fremdwährung;Betrag;Kurs;Betrag;Währung",
    `${today(false)};${today(false)};AUSLANDSEINSATZENTGELT;EUR;${fee};0,00000;${fee};EUR`,
    `${today(false)};${today(false)};PAYPAL *${shop}, 12345 0000000000, DE;USD;-1,00;1,10000;${purchase};EUR`,
    "Saldo:;;;;;;0,00;EUR",
  ];
  return { name: "karte.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

function giroCsv(iban: string, who: string, amount: string) {
  const lines = [
    "Umsätze",
    "Konto;Filial-/Kontonummer;IBAN;Währung",
    `Giro;000 0000000 00;${iban};EUR`,
    "",
    "Buchungstag;Wert;Umsatzart;Begünstigter / Auftraggeber;Verwendungszweck;IBAN / Kontonummer;BIC;Kundenreferenz;" +
      "Mandatsreferenz;Gläubiger ID;Fremde Gebühren;Betrag;Abweichender Empfänger;Anzahl der Aufträge;Anzahl der Schecks;Soll;Haben;Währung",
    `${today()};${today()};Lastschrift;${who};Kreditkartenabrechnung;;;;;;;${amount};;;;;;EUR`,
  ];
  return { name: "giro.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

test("credit card: own account, shop without PayPal, giro debit ignored as card statement", async ({ page }, info) => {
  const { card, giro, amounts, total } = DATA[info.project.name];
  const shop = `KARTENSHOP${info.project.name.toUpperCase()}${Date.now()}`;
  await login(page);
  await page.goto("/bank");

  await page.getByTestId("statement-input").setInputFiles(cardCsv(card, shop, amounts));
  await expect(toast(page, "success").filter({ hasText: `Kreditkarte …${card.slice(-4)}` })).toBeVisible();
  // the shop is the counterparty, the euro amount after the exchange rate counts
  const purchase = page.getByTestId("booking-row").filter({ hasText: shop }).first();
  await expect(purchase).toContainText(amounts[0].slice(1));

  const payer = `Kartenbank ${info.project.name} ${Date.now()}`;
  await page.getByTestId("statement-input").setInputFiles(giroCsv(giro, payer, total));
  await expect(toast(page, "success").filter({ hasText: "1 Kreditkartenabrechnung(en)" })).toBeVisible();
  await page.getByRole("tab", { name: "Ignoriert" }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: payer })).toContainText("Kartenabrechnung");

  // settings show the card, no IBAN field for it
  await page.goto("/settings");
  await expect(page.getByTestId("account-card").filter({ hasText: `…${card.slice(-4)}` })).toBeVisible();
});
