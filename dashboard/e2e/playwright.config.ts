import { defineConfig, devices } from "@playwright/test";

const supplied = process.env.LEADZEN_E2E_BASE_URL;
if (!supplied) throw new Error("LEADZEN_E2E_BASE_URL must be an explicitly authorized synthetic HTTPS candidate");
const origin = new URL(supplied);
if (origin.protocol !== "https:" || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
  throw new Error("Browser verification requires an exact trusted HTTPS origin");
}
if (!process.env.LEADZEN_E2E_FIXTURE_FILE) throw new Error("A private disposable LEADZEN_E2E_FIXTURE_FILE is required");

export default defineConfig({
  testDir: ".",
  testMatch: "production.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0, // Setup capabilities/password changes are deliberately single-use.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  outputDir: process.env.LEADZEN_E2E_RESULTS_DIR || "../e2e-results",
  use: {
    baseURL: origin.origin,
    ignoreHTTPSErrors: false,
    trace: "off", video: "off", screenshot: "off",
    serviceWorkers: "block",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "trusted-https-chromium" }],
});
