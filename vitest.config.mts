import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests of the pure helpers in lib/ (no browser, no servers).
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: { include: ["lib/**/*.test.ts"], environment: "node" },
});
