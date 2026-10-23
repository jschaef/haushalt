import { expect, test, type Page } from "@playwright/test";
import { login, pdf, png, toast } from "./helpers";

test.use({ locale: "de-DE" });

const YEAR = new Date().getFullYear();

/** Creates a meter without a meter number (so photo/bill matching never picks it by number). */
async function createMeter(page: Page, name: string) {
  await page.goto("/utilities");
  await page.getByLabel("Bezeichnung").fill(name);
  await page.getByRole("button", { name: "Hinzufügen", exact: true }).click();
  const card = page.getByTestId("meter-card").filter({ hasText: name });
  await expect(card).toBeVisible();
  return card;
}

async function openDetails(card: ReturnType<Page["getByTestId"]>) {
  await card.getByRole("button", { name: "Details", exact: true }).click();
  await expect(card.getByRole("region", { name: "Zählerstände", exact: true })).toBeVisible();
}

async function addReading(card: ReturnType<Page["getByTestId"]>, date: string, value: string) {
  const readings = card.getByRole("region", { name: "Zählerstände", exact: true });
  await readings.getByLabel("Datum").fill(date);
  await readings.getByLabel("Zählerstand").fill(value);
  await readings.getByRole("button", { name: "Hinzufügen" }).click();
}

test("meter form defaults, readings give consumption, tariff and instalment give a forecast", async ({ page }, testInfo) => {
  const name = `Strom ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  await page.goto("/utilities");

  // the link to the fixed costs (not in the phone tab bar)
  await expect(page.locator('main a[href="/fixed"]')).toBeVisible();

  // unit and category follow the kind until the user changes them
  await expect(page.getByLabel("Einheit")).toHaveValue("kWh");
  await expect(page.getByLabel("Kategorie").locator("option:checked")).toHaveText("Strom");
  await page.getByLabel("Art").selectOption({ label: "Wasser" });
  await expect(page.getByLabel("Einheit")).toHaveValue("m³");
  await page.getByLabel("Art").selectOption({ label: "Strom" });
  await expect(page.getByLabel("Einheit")).toHaveValue("kWh");

  const card = await createMeter(page, name);
  await expect(toast(page, "success").first()).toBeVisible();
  await expect(card).toContainText("kWh");

  await openDetails(card);
  await addReading(card, `${YEAR}-01-01`, "100");
  await expect(card.getByTestId("reading-list")).toContainText("100 kWh");
  await addReading(card, `${YEAR}-01-11`, "110");
  await expect(card.getByTestId("reading-list").locator("li")).toHaveCount(2);

  const stats = card.getByTestId("meter-stats");
  await expect(stats).toContainText(/Verbrauch bisher\s*10 kWh/);
  await expect(stats).toContainText(/Pro Tag\s*1 kWh/);
  // no tariff and no instalment yet: no forecast
  await expect(card.getByTestId("forecast")).toHaveCount(0);

  const tariffs = card.getByRole("region", { name: "Tarife", exact: true });
  await tariffs.getByLabel("Gültig ab").fill(`${YEAR}-01-01`);
  await tariffs.getByLabel("Preis (ct pro kWh)").fill("30,5");
  await tariffs.getByLabel("Grundgebühr pro Monat").fill("12,00");
  await tariffs.getByRole("button", { name: "Hinzufügen" }).click();
  await expect(card.getByTestId("tariff-list")).toContainText(/30,5 ct\/kWh/);
  await expect(card.getByTestId("tariff-list")).toContainText(/12,00\s*€ pro Monat/);

  const instalment = card.getByRole("form", { name: "Monatlicher Abschlag" });
  await instalment.getByRole("textbox").fill("100,00");
  await instalment.getByRole("button", { name: "Abschlag anlegen" }).click();
  await expect(toast(page, "success").filter({ hasText: "Abschlag angelegt" })).toBeVisible();

  const forecast = card.getByTestId("forecast");
  await expect(forecast).toBeVisible();
  await expect(forecast).toHaveText(/(Guthaben|Nachzahlung)\s*\d/);
  await expect(forecast).toHaveAttribute("data-value", /^-?\d+$/);
  await expect(card).toContainText(/Empfohlener Abschlag/);

  // the instalment is a normal fixed cost linked to the meter
  await page.goto("/fixed");
  await expect(page.getByTestId("recurring-row").filter({ hasText: `${name} Abschlag` })).toBeVisible();
});

test("a decreasing reading is refused with an error toast", async ({ page }, testInfo) => {
  const name = `Zaehler fehler ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);
  await openDetails(card);
  await addReading(card, `${YEAR}-01-11`, "100");
  await expect(card.getByTestId("reading-list").locator("li")).toHaveCount(1);

  await addReading(card, `${YEAR}-01-21`, "50");
  await expect(toast(page, "error").first()).toBeVisible();
  await expect(card.getByTestId("reading-list").locator("li")).toHaveCount(1);
});

test("meter photo proposes the value, saving stores it as a photo reading", async ({ page }, testInfo) => {
  const name = `Zaehler foto ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);

  await page.getByTestId("meter-photo-input").setInputFiles(png("zaehler.png"));
  const confirm = page.getByTestId("photo-confirm");
  await expect(confirm).toBeVisible();
  await expect(confirm.getByLabel("Zählerstand")).toHaveValue("12345,6");
  // preselected when the photo matched exactly one meter, else pick it
  await confirm.getByLabel("Zähler", { exact: true }).selectOption({ label: name });
  await confirm.getByRole("button", { name: "Speichern" }).click();
  await expect(toast(page, "success").filter({ hasText: "Zählerstand gespeichert" })).toBeVisible();
  await expect(confirm).toHaveCount(0);

  await openDetails(card);
  const list = card.getByTestId("reading-list");
  await expect(list).toContainText(/12\.345,6 kWh/);
  await expect(list).toContainText("Foto");
});

test("bill upload shows the bill, can be assigned to a meter and applied", async ({ page }, testInfo) => {
  const name = `Zaehler rechnung ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);

  await page.getByTestId("bill-input").setInputFiles(pdf("abrechnung.pdf"));
  await expect(toast(page, "success").filter({ hasText: "Abrechnung hochgeladen" })).toBeVisible();

  // newest bill first
  const bill = page.getByTestId("bill-row").filter({ hasText: "Stadtwerke Beispiel" }).first();
  await expect(bill).toBeVisible();
  await expect(bill).toContainText(/Nachzahlung\s*60,00\s*€/);
  await expect(bill).toContainText(/960,00\s*€/);
  await expect(bill).toContainText(/900,00\s*€/);
  await expect(bill).toContainText(/85,00\s*€/);
  await expect(bill).toContainText(/2\.400 kWh/);
  const file = bill.locator("a[target=_blank]");
  await expect(file).toHaveAttribute("rel", /noopener/);
  await expect(file).toHaveAttribute("href", /\/api\/v1\/bills\/\d+\/file$/);

  await bill.getByLabel("Zähler zuordnen").selectOption({ label: name });
  const apply = bill.getByRole("button", { name: "Übernehmen" });
  await expect(apply).toBeEnabled();
  await apply.click();
  await expect(toast(page, "success").filter({ hasText: "Tarif und Abschlag übernommen" })).toBeVisible();

  // the tariff of the bill is now on the meter
  await openDetails(card);
  await expect(card.getByTestId("tariff-list")).toContainText(/32,5 ct\/kWh/);
});
