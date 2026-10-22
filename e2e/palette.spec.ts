import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ locale: "de-DE" });

test("Ctrl+K opens the palette, 'Fix' + Enter goes to /fixed", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcut: desktop only");
  await login(page);
  await page.waitForLoadState("networkidle");

  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const input = dialog.getByRole("combobox");
  await expect(input).toBeFocused();
  await input.fill("Fix");
  await expect(dialog.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Enter");
  await page.waitForURL("**/fixed");
  await expect(dialog).toHaveCount(0);
});
