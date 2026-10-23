import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers";

// Baseline: WCAG 2.2 level AA, the web requirements of EN 301 549 V4.1.1
// (European standard behind the BFSG). axe covers the automatable rules;
// reflow (1.4.10) and focus not obscured (2.4.11) are checked below.

test.use({ locale: "de-DE" });

const PAGES = ["/dashboard", "/receipts", "/fixed", "/utilities", "/bank", "/settings"];

async function violations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]).analyze();
  return result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
}

async function setTheme(page: Page, theme: string) {
  await page.evaluate((value) => localStorage.setItem("theme", value), theme);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(themeClass(theme));
}

// whole class names: "contrast" must not match "contrast-light"
function themeClass(theme: string) {
  return new RegExp(`(^|\\s)${theme}(\\s|$)`);
}

// low-vision modes: tiles are fully opaque from the first frame (no fade-in)
async function expectNoFadeIn(page: Page) {
  await page.goto("/utilities");
  await page.locator("section.glass").first().waitFor();
  const opacities = await page.locator("section.glass").evaluateAll((els) => els.map((el) => getComputedStyle(el).opacity));
  expect(opacities.length).toBeGreaterThan(0);
  expect(opacities.every((o) => o === "1"), opacities.join(" ")).toBe(true);
}

test("high-contrast mode: toggle, larger text, no transparency, persists", async ({ page }) => {
  await login(page);
  await setTheme(page, "dark");
  const toggle = page.getByTestId("contrast-toggle").filter({ visible: true });
  await toggle.click();
  const html = page.locator("html");
  await expect(html).toHaveClass(themeClass("contrast"));
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(parseFloat(await html.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(19);
  const glass = page.locator(".glass").first();
  expect(await glass.evaluate((el) => getComputedStyle(el).backdropFilter)).toBe("none");
  await expectNoFadeIn(page);
  expect(await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(0, 0, 0)");
  // larger text must not push anything off narrow screens
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
  }
  await page.reload();
  await expect(html).toHaveClass(themeClass("contrast"));
  await page.getByTestId("contrast-toggle").filter({ visible: true }).click();
  await expect(html).toHaveClass(themeClass("dark"));
});

test("light low-vision mode: from the light theme, black on white, sun/moon keeps the mode", async ({ page }) => {
  await login(page);
  await setTheme(page, "light");
  const html = page.locator("html");
  const toggle = page.getByTestId("contrast-toggle").filter({ visible: true });
  await toggle.click();
  await expect(html).toHaveClass(themeClass("contrast-light"));
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(parseFloat(await html.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(19);
  expect(await page.locator(".glass").first().evaluate((el) => getComputedStyle(el).backdropFilter)).toBe("none");
  await expectNoFadeIn(page);
  const body = page.locator("body");
  expect(await body.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(255, 255, 255)");
  expect(await body.evaluate((el) => getComputedStyle(el).color)).toBe("rgb(0, 0, 0)");
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
  }
  // light/dark switch stays in the low-vision mode
  const lightness = page.getByRole("button", { name: "Hell/Dunkel umschalten" }).filter({ visible: true });
  await lightness.click();
  await expect(html).toHaveClass(themeClass("contrast"));
  await lightness.click();
  await expect(html).toHaveClass(themeClass("contrast-light"));
  await page.reload();
  await expect(html).toHaveClass(themeClass("contrast-light"));
  await toggle.click();
  await expect(html).toHaveClass(themeClass("light"));
  // also selectable in the settings
  await page.goto("/settings");
  await page.getByRole("button", { name: "Hoher Kontrast hell" }).click();
  await expect(html).toHaveClass(themeClass("contrast-light"));
});

for (const theme of ["contrast", "contrast-light", "dark", "light"]) {
  test(`no serious accessibility violations (${theme})`, async ({ page }) => {
    // every theme must pass WCAG AA, the low-vision modes included
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

for (const theme of ["dark", "contrast", "contrast-light"]) {
  test(`reflow: no sideways scrolling at 320 CSS px (${theme})`, async ({ page }) => {
    // WCAG 1.4.10: content usable at 320 px width without horizontal scrolling
    await page.setViewportSize({ width: 320, height: 640 });
    await login(page);
    await setTheme(page, theme);
    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${path} scrolls sideways at 320 px`).toBeLessThanOrEqual(0);
    }
  });
}

test("focus is not hidden behind the sticky header or the tab bar", async ({ page, isMobile }) => {
  // WCAG 2.4.11: a focused element must not be entirely covered
  await login(page);
  await setTheme(page, "contrast");
  for (const path of ["/settings", "/fixed"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const hidden = await page.evaluate((mobile) => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        if (el.closest("header, nav[aria-label=Main]")) return null;
        const r = el.getBoundingClientRect();
        const covers = [document.querySelector("header > div"), mobile ? document.querySelector("nav[aria-label=Main] > div") : null]
          .filter(Boolean)
          .map((c) => (c as HTMLElement).getBoundingClientRect());
        const covered = covers.some((c) => r.top >= c.top && r.bottom <= c.bottom && r.left >= c.left && r.right <= c.right);
        return covered ? `${el.tagName} ${el.textContent?.trim().slice(0, 30) ?? ""}` : null;
      }, !!isMobile);
      expect(hidden, `${path}: focus hidden after ${i + 1} tabs`).toBeNull();
    }
  }
});
