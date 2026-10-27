import { expect, test } from "@playwright/test";
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

test("supermarket payments count as groceries, the list is editable", async ({ page }, info) => {
  const stamp = `${info.project.name}${Date.now()}`;
  await login(page);

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(statement([[`REWE Markt ${stamp}`, "Einkauf", "-12,34"]]));
  await expect(toast(page, "success")).toBeVisible();
  await page.getByRole("tab", { name: "Alle", exact: true }).click();
  const rewe = page.getByTestId("booking-row").filter({ hasText: stamp });
  await expect(rewe).toContainText("Lebensmittel");

  // a merchant added in the settings counts the next import
  await page.goto("/settings");
  const tile = page.getByTestId("merchants-tile");
  await expect(tile.getByTestId("merchant-row").filter({ hasText: "norma" })).toBeVisible();
  await tile.getByLabel("Stichwort im Empfänger").fill(`Hofladen${stamp}`);
  await tile.getByLabel("Kategorie", { exact: true }).selectOption({ label: "Drogerie" });
  await tile.getByRole("button", { name: "Händler hinzufügen" }).click();
  await expect(toast(page, "success").filter({ hasText: "Händler hinzugefügt" })).toBeVisible();
  const row = tile.getByTestId("merchant-row").filter({ hasText: `hofladen${stamp}` });
  await expect(row).toBeVisible();

  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(statement([[`Hofladen${stamp}`, "Eier", "-4,50"]]));
  await expect(toast(page, "success")).toBeVisible();
  await page.getByRole("tab", { name: "Alle", exact: true }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: "Eier" }).filter({ hasText: stamp })).toContainText("Drogerie");

  await page.goto("/settings");
  await page.getByTestId("merchants-tile").getByRole("button", { name: `hofladen${stamp.toLowerCase()} entfernen` }).click();
  await expect(toast(page, "success").filter({ hasText: "Händler entfernt" })).toBeVisible();
});
