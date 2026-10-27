import { expect, test } from "@playwright/test";
import { login, toast } from "./helpers";

test.use({ locale: "de-DE" });

const PNG_1PX = Buffer.from(
  "89504e470d0a1a0a0000000d4948445200000001000000010806000000" +
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082",
  "hex",
);

test("a script uploads and reads with an API token until it is revoked", async ({ page, playwright, baseURL }, info) => {
  const name = `Scanner ${info.project.name}${Date.now()}`;
  await login(page);
  await page.goto("/settings");
  const tile = page.getByTestId("api-tokens-tile");
  await tile.getByLabel("Wofür (z. B. Scanner)").fill(name);
  await tile.getByRole("button", { name: "Token erstellen" }).click();
  await expect(toast(page, "success").filter({ hasText: "Token erstellt" })).toBeVisible();
  const token = (await tile.getByTestId("api-token-value").textContent())?.trim() ?? "";
  expect(token).toMatch(/^hh_/);
  await tile.getByRole("button", { name: "Fertig" }).click();
  await expect(tile.getByTestId("api-token-value")).toHaveCount(0);

  // a script: no cookie, no Origin, only the token
  const script = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
  const uploaded = await script.post("/api/v1/receipts", {
    multipart: { files: { name: "bon.png", mimeType: "image/png", buffer: PNG_1PX } },
  });
  expect(uploaded.status()).toBe(201);
  expect((await script.get("/api/v1/stats/summary")).status()).toBe(200);
  expect((await script.post("/api/v1/tags", { data: { name: "nein" } })).status()).toBe(403);

  await page.reload();
  const row = tile.getByTestId("api-token-row").filter({ hasText: name });
  await expect(row).toContainText("zuletzt benutzt");
  page.once("dialog", (dialog) => void dialog.accept());
  await row.getByRole("button", { name: `${name} widerrufen` }).click();
  await expect(toast(page, "success").filter({ hasText: "Token widerrufen" })).toBeVisible();
  expect((await script.get("/api/v1/stats/summary")).status()).toBe(401);
  await script.dispose();

  // without any credentials the gateway still answers 401
  const anonymous = await playwright.request.newContext({ baseURL });
  expect((await anonymous.get("/api/v1/stats/summary")).status()).toBe(401);
  await anonymous.dispose();
});
