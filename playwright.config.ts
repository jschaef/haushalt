import { defineConfig, devices } from "@playwright/test";

// The e2e tests need both servers: haushalt-api from backend/ (port 8300,
// empty temporary data directory, fake receipt reader - no Anthropic calls)
// and this app (port 3200, production build: run `npm run build` first).
// Already running servers are reused, so a reused API must never be a
// production one. HAUSHALT_E2E_PYTHON selects the interpreter (default: the
// venv in backend/.venv).
const python = process.env.HAUSHALT_E2E_PYTHON ?? ".venv/bin/python";
const port = Number(process.env.PORT ?? 3200);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // one shared database: tests run in order, the first one creates the household
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `${python} -m haushalt_api.e2e_server --port 8300`,
      cwd: "backend",
      url: "http://127.0.0.1:8300/api/v1/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `npx next start -p ${port}`,
      url: `http://127.0.0.1:${port}/login`,
      reuseExistingServer: true,
      timeout: 60_000,
      // plain HTTP in tests: the session cookie must not be Secure
      env: { HAUSHALT_COOKIE_SECURE: "false", HAUSHALT_API_URL: "http://127.0.0.1:8300" },
    },
  ],
});
