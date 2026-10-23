import { expect, test, type Browser, type Page } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

const GOOD = "Brotkorb mit Mohn und Sesam";

async function loginAs(page: Page, username: string, password: string) {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Anmelden" })).toBeVisible();
  await page.getByLabel("Benutzername").fill(username);
  await page.getByLabel("Passwort").fill(password);
  await page.getByRole("button", { name: "Anmelden" }).click();
}

async function memberPage(browser: Browser) {
  const context = await browser.newContext({ locale: "de-DE" });
  return { context, page: await context.newPage() };
}

async function addMember(page: Page, username: string, name: string): Promise<string> {
  await page.goto("/settings");
  await page.getByLabel("Benutzername").fill(username);
  await page.getByLabel("Anzeigename", { exact: true }).last().fill(name);
  await page.getByRole("button", { name: "Hinzufügen" }).first().click();
  const panel = page.getByTestId("one-time-password");
  await expect(panel).toContainText(`Einmal-Passwort für ${name}`);
  const password = (await panel.locator("p.font-mono").textContent())!.trim();
  expect(password).toMatch(/^[a-z2-9]{5}(-[a-z2-9]{5}){3}$/);
  await panel.getByRole("button", { name: "Fertig" }).click();
  await expect(panel).toBeHidden();
  return password;
}

test("admin adds a member, the one-time password must be replaced, weak passwords are refused", async ({ page, browser }, info) => {
  const username = `mia${info.project.name}${Date.now()}`;
  await login(page);
  const oneTime = await addMember(page, username, "Mia");
  await expect(page.getByTestId("member").filter({ hasText: username })).toContainText("Einmal-Passwort offen");

  const member = await memberPage(browser);
  await loginAs(member.page, username, oneTime);
  await member.page.waitForURL("**/password**");
  // other pages send back to the password page as long as the one-time password is active
  await member.page.goto("/receipts");
  await member.page.waitForURL("**/password**");

  const form = member.page.getByTestId("password-form");
  await expect(form).toContainText("Du hast dich mit einem Einmal-Passwort angemeldet");
  await form.getByLabel("Einmal-Passwort").fill(oneTime);
  await form.getByLabel("Neues Passwort", { exact: true }).fill("kurz");
  await expect(form).toContainText("Zu kurz: mindestens 12 Zeichen.");
  await expect(form.getByRole("button", { name: "Passwort speichern" })).toBeDisabled();
  await form.getByLabel("Neues Passwort", { exact: true }).fill("iloveyou1234");
  await form.getByLabel("Neues Passwort wiederholen").fill("iloveyou1234");
  await form.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(form.getByRole("alert")).toContainText("geleakter");

  await form.getByLabel("Neues Passwort", { exact: true }).fill(GOOD);
  await form.getByLabel("Neues Passwort wiederholen").fill(GOOD + "x");
  await expect(form).toContainText("stimmen nicht überein");
  await form.getByLabel("Neues Passwort wiederholen").fill(GOOD);
  await form.getByRole("button", { name: "Passwort speichern" }).click();
  await member.page.waitForURL("**/receipts");

  // members see everybody but manage nobody
  await member.page.goto("/settings");
  await expect(member.page.getByText("Mitglieder anlegen und verwalten können nur Admins.")).toBeVisible();
  await expect(member.page.getByRole("button", { name: "Passwort zurücksetzen" })).toHaveCount(0);
  await member.context.close();
});

test("reset ends the member's sessions, disabling blocks the login", async ({ page, browser }, info) => {
  const username = `tom${info.project.name}${Date.now()}`;
  await login(page);
  const oneTime = await addMember(page, username, "Tom");
  const member = await memberPage(browser);
  await loginAs(member.page, username, oneTime);
  await member.page.waitForURL("**/password**");
  const form = member.page.getByTestId("password-form");
  await form.getByLabel("Einmal-Passwort").fill(oneTime);
  await form.getByLabel("Neues Passwort", { exact: true }).fill(GOOD);
  await form.getByLabel("Neues Passwort wiederholen").fill(GOOD);
  await form.getByRole("button", { name: "Passwort speichern" }).click();
  await member.page.waitForURL("**/dashboard");

  // reset: a new one-time password, the member's session ends
  const row = page.getByTestId("member").filter({ hasText: username });
  page.once("dialog", (dialog) => void dialog.accept());
  await row.getByRole("button", { name: "Passwort zurücksetzen" }).click();
  const panel = page.getByTestId("one-time-password");
  await expect(panel).toContainText("Einmal-Passwort für Tom");
  const second = (await panel.locator("p.font-mono").textContent())!.trim();
  expect(second).not.toBe(oneTime);
  await panel.getByRole("button", { name: "Fertig" }).click();
  await member.page.goto("/receipts");
  await member.page.waitForURL("**/login**");
  await loginAs(member.page, username, GOOD);
  await expect(member.page.locator("p[role=alert]")).toContainText("Anmeldung fehlgeschlagen");

  // disable: even the right password does not get in
  page.once("dialog", (dialog) => void dialog.accept());
  await row.getByRole("button", { name: "Sperren" }).click();
  await expect(row).toContainText("Gesperrt");
  await loginAs(member.page, username, second);
  await expect(member.page.locator("p[role=alert]")).toContainText("Dieses Konto ist gesperrt");
  await row.getByRole("button", { name: "Entsperren" }).click();
  await expect(row).not.toContainText("Gesperrt");
  await member.context.close();
});

test("own password change checks the current password", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  const form = page.getByTestId("password-form");
  await form.getByLabel("Aktuelles Passwort").fill("falsch-falsch-falsch");
  await form.getByLabel("Neues Passwort", { exact: true }).fill(GOOD);
  await form.getByLabel("Neues Passwort wiederholen").fill(GOOD);
  await form.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(form.getByRole("alert")).toContainText("Das aktuelle Passwort stimmt nicht.");
  // the admin cannot reset, demote or disable themselves
  await expect(page.getByTestId("member").filter({ hasText: "@jochen" }).getByRole("button")).toHaveCount(0);
});
