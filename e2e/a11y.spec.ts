import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

const PAGES = ["/dashboard", "/receipts", "/fixed", "/utilities", "/bank", "/settings"];

async function violations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
}

async function setTheme(page: Page, theme: string) {
  await page.evaluate((value) => localStorage.setItem("theme", value), theme);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(new RegExp(`\\b${theme}\\b`));
}

test("high-contrast mode: toggle, larger text, no transparency, persists", async ({ page }) => {
  await login(page);
  await setTheme(page, "dark");
  const toggle = page.getByTestId("contrast-toggle").filter({ visible: true });
  await toggle.click();
  const html = page.locator("html");
  await expect(html).toHaveClass(/\bcontrast\b/);
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(parseFloat(await html.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(19);
  const glass = page.locator(".glass").first();
  expect(await glass.evaluate((el) => getComputedStyle(el).backdropFilter)).toBe("none");
  expect(await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(0, 0, 0)");
  await page.reload();
  await expect(html).toHaveClass(/\bcontrast\b/);
  await page.getByTestId("contrast-toggle").filter({ visible: true }).click();
  await expect(html).toHaveClass(/\bdark\b/);
});

for (const theme of ["contrast", "dark", "light"]) {
  test(`no serious accessibility violations (${theme})`, async ({ page }) => {
    // dark/light are checked for structure and contrast as well; the
    // contrast theme must pass everything at WCAG AA
    await login(page);
    await setTheme(page, theme);
    const found: string[] = [];
    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      // animations finished (tiles fade in)
      await page.waitForTimeout(800);
      for (const violation of await violations(page)) found.push(`${path} ${violation}`);
    }
    expect(found).toEqual([]);
  });
}

test("login page has no serious accessibility violations", async ({ page }) => {
  await page.goto("/login");
  await page.waitForTimeout(800);
  expect(await violations(page)).toEqual([]);
});
