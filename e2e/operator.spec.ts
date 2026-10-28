import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

// created by the e2e server (backend/haushalt_api/e2e_server.py)
const OPERATOR = { username: "betreiber", password: "Leuchtturm-am-Deich-27" };

test("the operator creates a household with its admin and disables it", async ({ page }, info) => {
  // the first household exists (its signup), then the operator logs in
  await login(page);
  // leave the app first: the dashboard's requests would answer 401 once the
  // cookie is gone and send the page to /login themselves (aborting goto)
  await page.goto("about:blank");
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/Benutzername/).fill(OPERATOR.username);
  await page.getByLabel(/Passwort/).fill(OPERATOR.password);
  await page.getByRole("button", { name: /Anmelden/ }).click();
  await page.waitForURL("**/operator");

  const name = `Nachbarn ${info.project.name} ${Date.now()}`;
  const form = page.getByTestId("new-household");
  await form.getByLabel("Name des Haushalts").fill(name);
  await form.getByLabel("Benutzername des Admins").fill(`lena-${info.project.name}-${Date.now()}`);
  await form.getByRole("button", { name: "Haushalt anlegen" }).click();
  await expect(page.getByTestId("one-time-password")).toBeVisible();

  const row = page.getByTestId("household-row").filter({ has: page.locator(`input[value="${name}"]`) });
  await expect(row).toContainText("1 Mitglieder");
  await row.getByRole("button", { name: "Sperren" }).click();
  await expect(row.getByText("Gesperrt")).toBeVisible();
  await row.getByRole("button", { name: "Entsperren" }).click();
  await expect(row.getByText("Gesperrt")).toHaveCount(0);

  // the household pages send the operator back here
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/operator$/);
  await expect(page.getByTestId("new-household")).toBeVisible();

  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
});
