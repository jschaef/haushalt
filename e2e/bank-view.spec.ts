import { expect, test } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

function csv(rows: [string, string, string][]) {
  const lines = ["Buchungstag;Empfänger;Verwendungszweck;Betrag", ...rows.map(([day, who, amount]) => `${day};${who};Kauf;${amount}`)];
  return { name: "auszug.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n"), "utf-8") };
}

test("bank list: sort by amount, filter by category and year, show more", async ({ page }, info) => {
  const stamp = `${info.project.name}${Date.now()}`;
  await login(page);
  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(
    csv([
      ["15.03.2024", `Klein ${stamp}`, "-5,00"],
      ["16.03.2024", `Gross ${stamp}`, "-500,00"],
      ["17.03.2024", `Mittel ${stamp}`, "-50,00"],
      ["01.02.2023", `Alt ${stamp}`, "-7,00"],
      // enough rows of one year for a second page
      ...Array.from({ length: 105 }, (_, i): [string, string, string] => [`01.06.2022`, `Viele ${stamp} ${i}`, `-1,${String(i).padStart(2, "0")}`]),
    ]),
  );
  await expect(toast(page, "success").filter({ hasText: "109 neu" })).toBeVisible();

  // a category of its own, "Gross" counts in it
  const category = `Scheune ${stamp}`;
  await page.evaluate(
    async ({ name, who }) => {
      const json = { "content-type": "application/json" };
      const created = await (await fetch("/api/v1/categories", { method: "POST", headers: json, body: JSON.stringify({ key: `scheune_${Date.now()}`, name_de: name, name_en: name, kind: "variable", color: "#8a4500", icon: "" }) })).json();
      const all = await (await fetch("/api/v1/bank/transactions?limit=20000")).json();
      const booking = all.find((b: { counterparty: string }) => b.counterparty === who);
      await fetch(`/api/v1/bank/transactions/${booking.id}`, { method: "PATCH", headers: json, body: JSON.stringify({ status: "counted", category_id: created.id }) });
    },
    { name: category, who: `Gross ${stamp}` },
  );
  await page.reload();
  await page.getByRole("tab", { name: "Alle" }).click();
  const toolbar = page.getByTestId("bank-toolbar");
  const rows = page.getByTestId("booking-row").filter({ hasText: stamp });

  // year filter
  await toolbar.getByLabel("Jahr").selectOption("2024");
  await expect(rows).toHaveCount(3);
  // sorted by amount: the biggest spending first
  await toolbar.getByLabel("Sortieren").selectOption({ label: "Betrag, größte Ausgabe zuerst" });
  await expect(rows.first()).toContainText(`Gross ${stamp}`);
  await expect(rows.last()).toContainText(`Klein ${stamp}`);
  // category filter
  await toolbar.getByLabel("Kategorie").selectOption({ label: category });
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText(`Gross ${stamp}`);
  await toolbar.getByLabel("Kategorie").selectOption({ label: "Alle Kategorien" });

  // more than 100 bookings: the first 100, then the rest on request
  await toolbar.getByLabel("Jahr").selectOption("2022");
  await toolbar.getByLabel("Sortieren").selectOption({ label: "Datum, neueste zuerst" });
  await expect(page.getByText(/^100 von \d+ Buchungen$/)).toBeVisible();
  await page.getByRole("button", { name: /^Weitere \d+ anzeigen$/ }).click();
  // desktop has its 105 rows of 2022 now all shown; the phone run also sees
  // the desktop run's 105 rows (one database per test run): 200 of 210
  await expect(page.getByText(/^100 von \d+ Buchungen$/)).toHaveCount(0);
});
