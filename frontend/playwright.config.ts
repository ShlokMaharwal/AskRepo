import { defineConfig } from "@playwright/test";

const port = Number(process.env["ASKREPO_E2E_PORT"] ?? 4173);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid test port");
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180000,
  expect: { timeout: 20000 },
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    channel: process.platform === "win32" ? "msedge" : "chromium",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: process.env["ASKREPO_E2E_REUSE"] === "true",
    timeout: 120000,
  },
});
