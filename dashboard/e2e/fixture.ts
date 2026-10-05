import { test as base, expect, type Page } from "@playwright/test";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { basename, dirname, isAbsolute } from "node:path";

type Account = { email: string; id: number; contact_id?: number };
type Manifest = { schema: number; fixture_id: string; candidate_sha256: string; provider_disabled: boolean; public_origin: string; database_directory: string; password: string; setup_token: string; accounts: Record<string, Account> };

function loadManifest(): Manifest {
  const file = process.env.LEADZEN_E2E_FIXTURE_FILE;
  if (!file || !isAbsolute(file)) throw new Error("Use an absolute private fixture manifest path");
  const canonical = realpathSync(file);
  const directory = dirname(canonical);
  if (!basename(directory).startsWith("leadzen-e2e.") || (statSync(canonical).mode & 0o077) !== 0 || (statSync(directory).mode & 0o077) !== 0) {
    throw new Error("Fixture manifest and disposable directory must be private");
  }
  const value = JSON.parse(readFileSync(canonical, "utf8")) as Manifest;
  if (value.schema !== 1 || value.provider_disabled !== true || realpathSync(value.database_directory) !== directory || value.public_origin !== new URL(process.env.LEADZEN_E2E_BASE_URL!).origin || !/^[a-f0-9]{32}$/.test(value.fixture_id) || !/^[a-f0-9]{64}$/.test(value.candidate_sha256)) {
    throw new Error("Candidate origin and disposable fixture identity do not match");
  }
  return value;
}

export const test = base.extend<{ fixture: Manifest; browserErrors: string[]; expectedHTTPFailures: Set<string> }>({
  expectedHTTPFailures: async ({}, use) => { await use(new Set()); },
  fixture: async ({ request }, use) => {
    const fixture = loadManifest();
    const response = await request.get("/__e2e/status");
    expect(response.ok(), "The candidate must expose the test-only fixture identity gate").toBe(true);
    const status = await response.json();
    expect(status).toMatchObject({ schema: 1, fixture_id: fixture.fixture_id, candidate_sha256: fixture.candidate_sha256, provider_disabled: true, production_settings: true, blocked_external_calls: 0 });
    await use(fixture);
    const final = await (await request.get("/__e2e/status")).json();
    expect(final.blocked_external_calls, "No external operation should even be attempted").toBe(0);
  },
  browserErrors: [async ({ page, expectedHTTPFailures }, use) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      // HTTP failures are checked against their actual URL/status below. This
      // avoids double counting Chrome's generic console message for an IDOR 404.
      if (message.type() === "error" && !/^Failed to load resource: the server responded with a status of /.test(message.text())) errors.push(message.text());
    });
    page.on("response", response => {
      const path = new URL(response.url()).pathname;
      if (response.status() >= 400 && !expectedHTTPFailures.has(`${path}:${response.status()}`)) errors.push(`HTTP ${response.status()} ${path}`);
    });
    page.on("requestfailed", request => {
      // Navigations cancel prefetches; actual fetch/asset/network failures fail.
      const failure = request.failure()?.errorText;
      if (failure && failure !== "net::ERR_ABORTED") errors.push(`Network failure ${new URL(request.url()).pathname}: ${failure}`);
    });
    await use(errors);
    expect(errors, "Console, hydration, CSP and upstream failures must fail the release gate").toEqual([]);
  }, { auto: true }],
});

export { expect };
export async function login(page: Page, fixture: Manifest, account = "ready", password = fixture.password) {
  await page.goto("/login");
  await page.getByLabel("Work email", { exact: true }).fill(fixture.accounts[account].email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
}

export async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "The document must fit the viewport; tables may scroll within their own region").toBe(true);
}

export async function contrast(page: Page, selector: string) {
  const ratio = await page.locator(selector).evaluate(element => {
    const channels = (value: string) => value.match(/[\d.]+/g)!.slice(0, 3).map(Number);
    const luminance = (values: number[]) => values.map(value => value / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
    const style = getComputedStyle(element);
    let parent: Element | null = element;
    let background = style.backgroundColor;
    while (background === "rgba(0, 0, 0, 0)" && parent?.parentElement) {
      parent = parent.parentElement;
      background = getComputedStyle(parent).backgroundColor;
    }
    const a = luminance(channels(style.color)), b = luminance(channels(background));
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
  expect(ratio, `Text contrast for ${selector}`).toBeGreaterThanOrEqual(4.5);
}
