import { expect, test } from "@playwright/test";
import { USER, login } from "./helpers";

test.use({ locale: "de-DE" });

test("unauthenticated dashboard redirects to login with next", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
});

test("wrong password shows an alert", async ({ page }) => {
  // make sure the household exists, then try again with a wrong password
  await login(page);
  await page.waitForLoadState("networkidle");
  await page.context().clearCookies();
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Anmelden" })).toBeVisible();
  await page.getByLabel("Benutzername").fill(USER.username);
  await page.getByLabel("Passwort").fill("definitely-wrong");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByText("Anmeldung fehlgeschlagen")).toBeVisible();
  await expect(page.locator("p[role=alert]")).toContainText("Anmeldung fehlgeschlagen");
  await expect(page).toHaveURL(/\/login/);
});

test("login lands on dashboard, logout returns to login", async ({ page }) => {
  await login(page);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("tile-total")).toBeVisible();

  await page.getByRole("button", { name: "Abmelden" }).click();
  await page.waitForURL("**/login");
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
});
