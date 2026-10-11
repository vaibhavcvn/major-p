import { defineConfig } from "@playwright/test";

/**
 * Playwright configuration — Smart Ambulance browser workflow tests.
 *
 * DATABASE ISOLATION:
 *   globalSetup (./tests/browser/global-setup.ts) seeds playwright_test.db
 *   (a fresh SQLite file) and starts an isolated backend on port 8000.
 *   The user's smart_ambulance.db is NEVER modified.
 *
 *   IMPORTANT: stop any running development backend on port 8000 before
 *   running Playwright tests. The global setup will start its own.
 *
 * SERVERS expected when running tests:
 *   Isolated backend: http://localhost:8000  (started by globalSetup)
 *   Frontend:         http://localhost:3000  (start manually: npm run dev)
 */
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],

  globalSetup:    "./tests/browser/global-setup.ts",
  globalTeardown: "./tests/browser/global-teardown.ts",

  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    permissions: ["geolocation"],
    geolocation: { latitude: 12.9716, longitude: 77.5946 },
  },

  projects: [
    {
      name: "chromium",
      use: {
        channel: "chrome",
        headless: true,
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
});
