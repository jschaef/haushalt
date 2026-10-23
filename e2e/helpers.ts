import { expect, type Locator, type Page } from "@playwright/test";

// meets the password policy (12+ characters, not common, no username)
export const USER = { username: "jochen", password: "Kassenbon-Sommer-2026" };

// 1x1 PNG; the fake receipt reader accepts any file with valid magic bytes.
export const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082",
  "hex",
);
export const PDF = Buffer.from("%PDF-1.4\n%fake\n");

export const png = (name = "bon.png") => ({ name, mimeType: "image/png", buffer: PNG });
export const pdf = (name = "bon.pdf") => ({ name, mimeType: "application/pdf", buffer: PDF });

/**
 * Logs in as the test household. The first call in a fresh database creates
 * the household (signup form), later calls use the login form.
 */
export async function login(page: Page) {
  const setup = page.waitForResponse((r) => r.url().includes("/api/v1/setup"));
  await page.goto("/login");
  const state = await (await setup).json();
  const needsSignup = Boolean(state.needs_first_user);
  // the signup form is visible once the setup answer has been rendered
  const submit = page.getByRole("button", { name: needsSignup ? /Haushalt anlegen|Create household/ : /Anmelden|Log in/ });
  await expect(submit).toBeVisible();
  await page.getByLabel(/Benutzername|Username/).fill(USER.username);
  if (needsSignup) await page.getByLabel(/Anzeigename|Display name/).fill("Jochen");
  await page.getByLabel(/Passwort|Password/).fill(USER.password);
  await submit.click();
  await page.waitForURL("**/dashboard");
}

/** Uploads one receipt from /receipts; resolves with its id once the editor is open. */
export async function uploadOne(page: Page, file = png()): Promise<number> {
  await page.goto("/receipts");
  await page.getByTestId("file-input").setInputFiles(file);
  await page.waitForURL(/\/receipts\/\d+$/);
  return Number(page.url().match(/\/receipts\/(\d+)$/)![1]);
}

/** Uploads one receipt and confirms it in the editor. */
export async function createConfirmedReceipt(page: Page): Promise<number> {
  const id = await uploadOne(page);
  const confirm = page.getByRole("button", { name: /^(Bestätigen|Confirm)$/ });
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await page.waitForURL(/\/receipts\?status=draft/);
  return id;
}

/** Target value in cents of the animated number inside a dashboard tile. */
export async function tileValue(page: Page, testId: string): Promise<number> {
  const number = page.getByTestId(testId).locator("[data-value]").first();
  await expect(number).toBeVisible();
  return Number(await number.getAttribute("data-value"));
}

export function toast(page: Page, type?: "success" | "error"): Locator {
  return page.locator(type ? `[data-sonner-toast][data-type="${type}"]` : "[data-sonner-toast]");
}
