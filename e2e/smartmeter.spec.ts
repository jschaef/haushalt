import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

const INGEST = "/api/v1/ingest/reading";

async function createMeter(page: Page, name: string) {
  await page.goto("/utilities");
  await page.getByLabel("Bezeichnung").fill(name);
  await page.getByRole("button", { name: "Hinzufügen", exact: true }).click();
  const card = page.getByTestId("meter-card").filter({ hasText: name });
  await expect(card).toBeVisible();
  return card;
}

type Card = Awaited<ReturnType<typeof createMeter>>;

async function openAuto(card: Card) {
  await card.getByRole("button", { name: "Automatisch ablesen", exact: true }).click();
  await expect(card.getByTestId("auto-section")).toBeVisible();
}

async function createToken(card: Card): Promise<string> {
  await card.getByRole("button", { name: "Geräte-Token erzeugen", exact: true }).click();
  const input = card.getByLabel("Geräte-Token", { exact: true });
  await expect(input).toBeVisible();
  const token = await input.inputValue();
  expect(token.startsWith("hhm_")).toBe(true);
  return token;
}

// no cookie and no Origin: a device, not a browser session
async function deviceClient(playwright: { request: { newContext: (o: { baseURL: string }) => Promise<APIRequestContext> } }, baseURL: string) {
  return playwright.request.newContext({ baseURL });
}

test("device token: push a reading through the gateway, see it in the card", async ({ page, playwright }, testInfo) => {
  const baseURL = testInfo.project.use.baseURL ?? "http://127.0.0.1:3200";
  const name = `Push ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);
  await openAuto(card);
  const token = await createToken(card);
  await expect(card.getByLabel("Beispielbefehl")).toHaveValue(new RegExp(`/api/v1/ingest/reading .*Bearer ${token}`));

  const device = await deviceClient(playwright, baseURL);
  const response = await device.post(INGEST, {
    headers: { Authorization: `Bearer ${token}` },
    data: { value: 1000.5 },
  });
  expect(response.status()).toBe(201);
  await device.dispose();

  // the token is gone after a reload, the reading and the time are there
  await page.reload();
  const again = page.getByTestId("meter-card").filter({ hasText: name });
  await expect(again).toBeVisible();
  await expect(again.getByLabel("Geräte-Token", { exact: true })).toHaveCount(0);
  await openAuto(again);
  await expect(again.getByTestId("last-ingest")).toContainText("Letzte automatische Ablesung");
  await again.getByRole("button", { name: "Details", exact: true }).click();
  const list = again.getByTestId("reading-list");
  await expect(list).toContainText("Gerät");
  await expect(list).toContainText(/1\.000,5/);
});

test("device push without or with a wrong token is rejected", async ({ playwright }, testInfo) => {
  const baseURL = testInfo.project.use.baseURL ?? "http://127.0.0.1:3200";
  const device = await deviceClient(playwright, baseURL);
  expect((await device.post(INGEST, { data: { value: 1 } })).status()).toBe(401);
  const garbage = await device.post(INGEST, { headers: { Authorization: "Bearer hhm_garbage" }, data: { value: 1 } });
  expect(garbage.status()).toBe(401);
  expect((await device.get(INGEST)).status()).toBe(405);
  await device.dispose();
});

test("pull source: local network only, errors are shown on the card", async ({ page }, testInfo) => {
  const name = `Pull ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);
  await openAuto(card);
  const url = card.getByLabel("Geräte-URL");
  const path = card.getByLabel("JSON-Pfad");

  // presets fill both fields
  await card.getByLabel("Vorlage").selectOption("tasmota");
  await expect(url).toHaveValue(/<device>/);
  await expect(path).not.toHaveValue("");
  await expect(card.getByText("Ersetze <device>")).toBeVisible();

  await url.fill("http://8.8.8.8/x");
  await path.fill("a.b");
  await card.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(toast(page, "error").first()).toBeVisible();

  await url.fill("http://127.0.0.1:8300/api/v1/health");
  await path.fill("status");
  await card.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(toast(page, "success").first()).toBeVisible();

  await card.getByRole("button", { name: "Jetzt abfragen", exact: true }).click();
  await expect(toast(page, "error").first()).toBeVisible();
  await expect(card.getByTestId("last-ingest-error")).toBeVisible();

  // switch off
  await card.getByRole("button", { name: "Abschalten", exact: true }).click();
  await expect(url).toHaveValue("");
  await expect(card.getByRole("button", { name: "Jetzt abfragen", exact: true })).toBeDisabled();
});

test("revoked token no longer works", async ({ page, playwright }, testInfo) => {
  const baseURL = testInfo.project.use.baseURL ?? "http://127.0.0.1:3200";
  const name = `Revoke ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);
  await openAuto(card);
  const token = await createToken(card);

  const device = await deviceClient(playwright, baseURL);
  const headers = { Authorization: `Bearer ${token}` };
  expect((await device.post(INGEST, { headers, data: { value: 5 } })).status()).toBe(201);

  page.once("dialog", (dialog) => dialog.accept());
  await card.getByRole("button", { name: "Token widerrufen", exact: true }).click();
  await expect(card.getByRole("button", { name: "Geräte-Token erzeugen", exact: true })).toBeVisible();

  expect((await device.post(INGEST, { headers, data: { value: 6 } })).status()).toBe(401);
  await device.dispose();
});

test("open automatic section is accessible and does not scroll sideways at 320 px", async ({ page }, testInfo) => {
  const name = `A11y ${testInfo.project.name} ${Date.now()}`;
  await login(page);
  const card = await createMeter(page, name);
  await openAuto(card);
  await createToken(card);
  await card.getByLabel("Vorlage").selectOption("tasmota");
  for (const theme of ["light", "dark", "contrast", "contrast-light"]) {
    await page.evaluate((value) => localStorage.setItem("theme", value), theme);
    await page.reload();
    const again = page.getByTestId("meter-card").filter({ hasText: name });
    await openAuto(again);
    await again.getByRole("button", { name: "Geräte-Token erzeugen", exact: false }).or(again.getByRole("button", { name: "Neues Token erzeugen" })).first().click();
    await again.getByLabel("Vorlage").selectOption("tasmota");
    await page.setViewportSize({ width: 320, height: 800 });
    await page.mouse.move(0, 0);
    await page.waitForTimeout(500); // let hover transitions settle before axe measures colors
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ") + " " + n.html.slice(0, 120)).join(" | ")}`);
    expect(serious, theme).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${theme} scrolls sideways`).toBeLessThanOrEqual(0);
  }
});
