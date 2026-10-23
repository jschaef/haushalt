import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

test("a category key with capitals is converted, an empty key comes from the name", async ({ page }, info) => {
  const stamp = `${info.project.name}${Date.now()}`;
  await login(page);
  await page.goto("/settings");
  const form = page.locator("form").filter({ hasText: "Kategorie hinzufügen" });
  const add = form.getByRole("button", { name: "Hinzufügen" });
  const hint = form.getByTestId("category-key-hint");

  // what Jochen typed: capital letters in the key
  await form.getByLabel("Schlüssel").fill(`Lotto ${stamp}`);
  await form.getByLabel("Name (Deutsch)").fill(`Lotto ${stamp}`);
  await form.getByLabel("Name (Englisch)").fill(`Lottery ${stamp}`);
  await expect(hint).toContainText(`„lotto_${stamp.toLowerCase()}“`);
  await expect(add).toBeEnabled();
  await add.click();
  await expect(page.getByText(`Lotto ${stamp}`, { exact: true })).toBeVisible();
  await expect(form.getByLabel("Schlüssel")).toHaveValue("");

  // no key typed: the German name gives it, umlauts spelled out
  await form.getByLabel("Name (Deutsch)").fill(`Müll & Gebühren ${stamp}`);
  await expect(hint).toContainText(`„muell_gebuehren_${stamp.toLowerCase()}“`);
  await expect(form.getByLabel("Schlüssel")).toHaveAttribute("placeholder", `muell_gebuehren_${stamp.toLowerCase()}`);
  await form.getByLabel("Name (Englisch)").fill(`Waste ${stamp}`);
  await add.click();
  await expect(page.getByText(`Müll & Gebühren ${stamp}`, { exact: true })).toBeVisible();

  // nothing usable in the key: the button stays off and the hint says why
  await form.getByLabel("Schlüssel").fill("!!!");
  await form.getByLabel("Name (Deutsch)").fill("x");
  await form.getByLabel("Name (Englisch)").fill("x");
  await expect(hint).toContainText("Mindestens 2 Zeichen.");
  await expect(form.getByLabel("Schlüssel")).toHaveAttribute("aria-invalid", "true");
  await expect(add).toBeDisabled();
});
