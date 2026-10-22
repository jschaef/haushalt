import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("foreign Origin on a changing request is rejected with 403", async ({ page }) => {
  await login(page);
  const response = await page.request.post("/api/v1/receipts", {
    headers: { Origin: "https://evil.example" },
    multipart: { files: { name: "a.png", mimeType: "image/png", buffer: Buffer.from("x") } },
  });
  expect(response.status()).toBe(403);
});

test("API without session cookie answers 401", async ({ playwright, baseURL }) => {
  const anonymous = await playwright.request.newContext({ baseURL });
  const response = await anonymous.get("/api/v1/me");
  expect(response.status()).toBe(401);
  await anonymous.dispose();
});

test("path traversal through the gateway is not served", async ({ page, playwright, baseURL }) => {
  await login(page);
  const anonymous = await playwright.request.newContext({ baseURL });
  for (const path of ["/api/v1/..%2Fhealth", "/api/v1/%2e%2e%2fhealth", "/api/v1/me%2f..%2f..%2fhealth", "/api/v1/..%5Chealth"]) {
    for (const client of [page.request, anonymous]) {
      const response = await client.get(path);
      expect([400, 404], `${path} -> ${response.status()}`).toContain(response.status());
    }
  }
  // a literal ".." segment is normalised by the client before sending
  const dotted = await page.request.get("/api/v1/receipts/../health");
  expect([200, 400, 404]).toContain(dotted.status());
  await anonymous.dispose();
});
