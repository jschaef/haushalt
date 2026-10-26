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
