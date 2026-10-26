import { defineConfig, devices } from "@playwright/test";

// E2E drives the real stack: backend (uvicorn, 127.0.0.1:8123) + frontend
// (`next start`, 127.0.0.1:3000). Both are started manually by the caller — see
// docs/DEPLOYMENT.md — so `baseURL` is the only wiring needed here.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
