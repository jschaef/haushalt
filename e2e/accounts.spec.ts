import { expect, test } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

// made-up IBANs with valid check digits, one pair per browser project
const IBANS: Record<string, { own: string; savings: string }> = {
  desktop: { own: "DE84100200300000001111", savings: "DE60100200300000002222" },
  phone: { own: "DE36100200300000003333", savings: "DE12100200300000004444" },
};

function today(): string {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

// Postbank layout: the own account above the table
function postbank(own: string, rows: [string, string, string, string][]) {
  const lines = [
    "Umsätze",
    "Konto;Filial-/Kontonummer;IBAN;Währung",
    `Giro;000 0000000 00;${own};EUR`,
    "",
    "Buchungstag;Wert;Umsatzart;Begünstigter / Auftraggeber;Verwendungszweck;IBAN / Kontonummer;BIC;Kundenreferenz;" +
      "Mandatsreferenz;Gläubiger ID;Fremde Gebühren;Betrag;Abweichender Empfänger;Anzahl der Aufträge;Anzahl der Schecks;Soll;Haben;Währung",
    ...rows.map(([who, why, iban, amount]) => `${today()};${today()};Überweisung;${who};${why};${iban};;;;;;${amount};;;;;;EUR`),
  ];
  return { name: "umsaetze.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

test("accounts: recognised on import, transfers ignored, incoming payments and account filter", async ({ page }, info) => {
  const { own, savings } = IBANS[info.project.name];
  const stamp = `${info.project.name}${Date.now()}`;
  await login(page);

  // the savings account is known before the statement comes in
  await page.goto("/settings");
  const tile = page.getByTestId("accounts-tile");
  await tile.getByLabel("Name").last().fill(`Sparkonto ${stamp}`);
  await tile.getByLabel("IBAN").last().fill(savings.replace(/(.{4})/g, "$1 "));
  await tile.getByRole("button", { name: "Konto hinzufügen" }).click();
  await expect(tile.getByRole("button", { name: `Konto „Sparkonto ${stamp}“ speichern` })).toBeVisible();

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(
    postbank(own, [
      [`Ich ${stamp}`, "Sparen", savings, "-100,00"],
      [`Arbeitgeber ${stamp}`, "Gehalt", "DE44500105175407324931", "2000,00"],
      [`Laden ${stamp}`, "Einkauf", "DE89370400440532013000", "-5,00"],
    ]),
  );
  const done = toast(page, "success").filter({ hasText: "3 neu" });
  await expect(done).toContainText(`Konto: Konto …${own.slice(-4)}.`);
  await expect(done).toContainText("1 Umbuchung(en) zwischen eigenen Konten ignoriert.");

  // only the purchase waits for review; it shows its account
  const purchase = page.getByTestId("booking-row").filter({ hasText: `Laden ${stamp}` });
  await expect(purchase.getByTestId("booking-account")).toContainText(`Konto …${own.slice(-4)}`);

  // incoming payments have their own tab
  await page.getByRole("tab", { name: "Eingänge" }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: `Arbeitgeber ${stamp}` })).toContainText("2.000,00");
  await expect(page.getByTestId("booking-row").filter({ hasText: `Laden ${stamp}` })).toHaveCount(0);

  // the transfer is ignored and says why
  await page.getByRole("tab", { name: "Ignoriert" }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: `Ich ${stamp}` })).toContainText("Umbuchung");

  // filter by account
  await page.getByRole("tab", { name: "Alle" }).click();
  await page.getByTestId("account-filter").getByRole("button", { name: `Sparkonto ${stamp}` }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: stamp })).toHaveCount(0);
  await page.getByTestId("account-filter").getByRole("button", { name: `Konto …${own.slice(-4)}` }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: stamp })).toHaveCount(3);

  // a statement of one account cannot be imported into another
  await page.getByTestId("import-account").selectOption({ label: `Sparkonto ${stamp}` });
  await page.getByTestId("statement-input").setInputFiles(postbank(own, [[`Kiosk ${stamp}`, "Zeitung", "", "-2,00"]]));
  await expect(toast(page, "error")).toContainText(own);
});
