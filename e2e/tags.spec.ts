import { expect, test, type Locator, type TestInfo } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

const unique = (info: TestInfo, label: string) => `${label}-${info.project.name}-${Date.now()}`;

function today(): string {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

function csv(counterparty: string, amount: string, purpose: string) {
  return {
    name: "auszug.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(`Buchungstag;Empfänger;Verwendungszweck;Betrag\n${today()};${counterparty};${purpose};${amount}\n`, "utf-8"),
  };
}

async function newTag(scope: Locator, name: string) {
  const picker = scope.getByTestId("tag-picker");
  await picker.getByPlaceholder("Neues Schlagwort").fill(name);
  await picker.getByRole("button", { name: "Schlagwort anlegen" }).click();
  await expect(picker.getByRole("button", { name, pressed: true })).toBeVisible();
}

test("fixed cost with a new tag: chip, filter and dashboard sum", async ({ page }, info) => {
  const tag = unique(info, "Kind");
  const cost = unique(info, "Sparplan");
  await page.goto("/fixed");
  // the add form is the first form on the page (no row is being edited)
  const form = page.locator("form").first();
  await form.getByLabel("Bezeichnung").fill(cost);
  await form.getByLabel("Betrag").fill("30,44");
  await newTag(form, tag);
  await form.getByRole("button", { name: "Hinzufügen" }).click();
  await expect(toast(page, "success")).toBeVisible();

  const row = page.getByTestId("recurring-row").filter({ hasText: cost });
  await expect(row.getByTestId("tag-chips")).toContainText(tag);
  // the filter shows only costs with that tag
  await page.getByTestId("tag-filter").getByRole("button", { name: tag }).click();
  await expect(page.getByTestId("recurring-row")).toHaveCount(1);
  await page.getByTestId("tag-filter").getByRole("button", { name: "Alle" }).click();

  await page.goto("/dashboard");
  await expect(page.getByTestId("tile-tags")).toContainText(tag);
});

test("a tag chosen with 'Zählt selbst' is learned for the counterparty", async ({ page }, info) => {
  const shop = unique(info, "Spielwaren");
  const tag = unique(info, "Geschenk");
  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(csv(shop, "-25,00", "Geschenk 1"));
  const booking = page.getByTestId("booking-row").filter({ hasText: shop }).filter({ hasText: "Geschenk 1" });
  await booking.getByRole("button", { expanded: false }).click();
  await booking.getByLabel("Zählt selbst").selectOption({ label: "Lifestyle" });
  await newTag(booking, tag);
  await booking.getByRole("button", { name: "Zuordnen" }).last().click();
  await expect(toast(page, "success").filter({ hasText: "Buchung aktualisiert" })).toBeVisible();

  // the next booking of the same counterparty is counted with the same tag
  await page.reload();
  await page.getByTestId("statement-input").setInputFiles(csv(shop, "-15,00", "Geschenk 2"));
  await expect(toast(page, "success").filter({ hasText: "1 neu" })).toBeVisible();
  await page.getByRole("tab", { name: "Gezählt" }).click();
  const second = page.getByTestId("booking-row").filter({ hasText: shop }).filter({ hasText: "Geschenk 2" });
  await expect(second.getByTestId("tag-chips")).toContainText(tag);

  // filter by the tag: both bookings
  await page.getByTestId("tag-filter").getByRole("button", { name: tag }).click();
  await expect(page.getByTestId("booking-row").filter({ hasText: shop })).toHaveCount(2);

  // rename in the settings, the new name shows on the booking
  await page.goto("/settings");
  const save = page.getByRole("button", { name: `Schlagwort „${tag}“ speichern` });
  const tagRow = page.getByTestId("tag-row").filter({ has: save });
  await tagRow.getByLabel("Name").fill(`${tag}-neu`);
  await save.click();
  await expect(page.getByRole("button", { name: `Schlagwort „${tag}-neu“ speichern` })).toBeVisible();
  await page.goto("/bank");
  await page.getByRole("tab", { name: "Gezählt" }).click();
  await expect(second.getByTestId("tag-chips")).toContainText(`${tag}-neu`);
});

test("a long tag name does not push the fixed-cost form off a 320 px screen", async ({ page }, info) => {
  // WCAG 1.4.10 reflow, in the high-contrast mode with its larger text
  const name = `${unique(info, "Sehr-langes-Schlagwort")}-`.padEnd(64, "x");
  await page.evaluate(async (tag) => {
    await fetch("/api/v1/tags", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: tag }) });
  }, name);
  await page.evaluate(() => localStorage.setItem("theme", "contrast"));
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/fixed");
  await expect(page.getByTestId("tag-picker").first()).toContainText(name.slice(0, 12));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("long category and tag names keep the bank decision panel on the screen", async ({ page }, info) => {
  const stamp = `${info.project.name}${Date.now()}`;
  await page.evaluate(async (s) => {
    const post = (path: string, body: unknown) =>
      fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    await post("/api/v1/categories", { key: `long_${s}`.toLowerCase(), name_de: `Sehr lange Kategorie mit Namen ${s}`, name_en: "Long", kind: "variable", color: "#123456", icon: "" });
    await post("/api/v1/tags", { name: `Ein-sehr-langes-Schlagwort-${s}`.padEnd(64, "x") });
  }, stamp);
  const shop = `Breit-${stamp}`;
  await page.goto("/bank");
  await page.getByTestId("statement-input").setInputFiles(csv(shop, "-1,00", "Breite"));
  const booking = page.getByTestId("booking-row").filter({ hasText: shop });
  await booking.getByRole("button", { expanded: false }).click();
  await booking.getByLabel("Zählt selbst").selectOption({ label: "Sonstiges" });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  // the button next to the select is reachable (it used to lie under it on phones)
  await booking.getByRole("button", { name: "Zuordnen" }).last().click();
  await expect(toast(page, "success").filter({ hasText: "Buchung aktualisiert" })).toBeVisible();
});
