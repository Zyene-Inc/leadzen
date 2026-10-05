import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { ThemeSync, ThemeToggle } from "@/components/theme-toggle";
import Dashboard from "@/components/overview";
import { themeBootstrap, themeStorageKey } from "@/lib/theme";
import { api } from "@/lib/client-api";
import { user } from "./fixtures";

const call = vi.mocked(api);
const bootstrap = () => new Function(themeBootstrap)();
const dark = () => screen.getByRole("radio", { name: "Dark mode" }) as HTMLInputElement;
const light = () => screen.getByRole("radio", { name: "Light mode" }) as HTMLInputElement;
const home = {
  operator_name: "Synthetic user",
  metrics: { found: 6, qualified: 3, with_email: 1, contacted: 0, replies: 0 },
  credits: { configured: false, balance: null, checked_at: null, synthetic: true },
  target: { summary: "", audience: null, country_name: "" },
  recent_activity: [],
};

beforeEach(() => {
  document.documentElement.dataset.theme = "light";
  localStorage.clear();
  call.mockReset();
});
afterEach(() => {
  document.documentElement.dataset.theme = "light";
  localStorage.clear();
});

for (let repetition = 1; repetition <= 10; repetition++) describe(`Theme pass ${repetition}`, () => {
  test("defaults to light and persists an explicit choice across remounts", async () => {
    bootstrap();
    const view = render(<ThemeToggle />);
    expect(light().checked).toBe(true);
    await userEvent.click(dark());
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(themeStorageKey)).toBe("dark");
    view.unmount();
    render(<ThemeToggle />);
    expect(dark().checked).toBe(true);
    await userEvent.click(light());
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(themeStorageKey)).toBe("light");
  });

  test("applies saved dark before hydration without a server/client mismatch", async () => {
    localStorage.setItem(themeStorageKey, "dark");
    const container = document.createElement("div");
    container.innerHTML = renderToString(<ThemeToggle />);
    document.body.append(container);
    bootstrap();
    expect(document.documentElement.dataset.theme).toBe("dark");
    const errors = vi.spyOn(console, "error");
    const root = hydrateRoot(container, <ThemeToggle />);
    try {
      await act(async () => {});
      expect(dark().checked).toBe(true);
      expect(errors).not.toHaveBeenCalled();
    } finally {
      act(() => root.unmount());
      container.remove();
    }
  });

  test("native radio keyboard controls work in both directions", async () => {
    const keyboard = userEvent.setup();
    render(<ThemeToggle />);
    await keyboard.tab();
    expect(document.activeElement).toBe(light());
    await keyboard.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(dark());
    expect(dark().checked).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    await keyboard.keyboard("{ArrowLeft}");
    expect(light().checked).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  test("works when storage writes are blocked", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Blocked", "SecurityError"); });
    render(<ThemeToggle />);
    await userEvent.click(dark());
    expect(dark().checked).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    await userEvent.click(light());
    expect(light().checked).toBe(true);
  });

  test("unavailable storage and invalid preferences safely use light", () => {
    localStorage.setItem(themeStorageKey, "unexpected-theme");
    bootstrap();
    expect(document.documentElement.dataset.theme).toBe("light");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("Blocked", "SecurityError"); });
    expect(bootstrap).not.toThrow();
    render(<ThemeToggle />);
    expect(light().checked).toBe(true);
  });

  test("follows other tabs and resets to light when a preference is removed", () => {
    render(<ThemeToggle />);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "dark" })));
    expect(dark().checked).toBe(true);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: "other.preference", newValue: "light" })));
    expect(dark().checked).toBe(true);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "light", storageArea: sessionStorage })));
    expect(dark().checked).toBe(true);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: null })));
    expect(light().checked).toBe(true);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "dark" })));
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: null })));
    expect(light().checked).toBe(true);
  });

  test("multiple controls share one preference and unique radio groups", async () => {
    render(<><ThemeToggle /><ThemeToggle /></>);
    const controls = screen.getAllByRole("radio", { name: "Dark mode" }) as HTMLInputElement[];
    expect(controls[0].name).not.toBe(controls[1].name);
    await userEvent.click(controls[0]);
    expect(controls.every(input => input.checked)).toBe(true);
  });

  test("pages without a theme control still follow changes from other tabs", () => {
    const page = render(<><ThemeSync /><p>Chat conversation</p></>);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "dark" })));
    expect(document.documentElement.dataset.theme).toBe("dark");
    page.rerender(<><ThemeSync /><ThemeToggle /></>);
    expect(dark().checked).toBe(true);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "light" })));
    expect(light().checked).toBe(true);
  });

  test("Dashboard places the theme in top actions and changes no application records", async () => {
    call.mockImplementation(async path => path === "overview"
      ? { home, ai_ready: false, mailboxes: [], activity: [] }
      : { items: [], total: 0 });
    render(<Dashboard user={user} />);
    const refresh = await screen.findByRole("button", { name: "Refresh" });
    const actions = refresh.closest(".top-actions") as HTMLElement;
    expect(within(actions).getByRole("group", { name: "Color theme" })).toBeTruthy();
    await waitFor(() => expect(call.mock.calls.some(([path]) => path === "attention")).toBe(true));
    const requests = call.mock.calls.length;
    await userEvent.click(dark());
    await userEvent.click(light());
    expect(call.mock.calls).toHaveLength(requests);
    expect(call.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });

  test("the theme control remains usable while loading and after a Dashboard error", async () => {
    call.mockRejectedValue(new Error("Synthetic workspace unavailable"));
    render(<Dashboard user={user} />);
    expect(screen.getByRole("group", { name: "Color theme" })).toBeTruthy();
    await screen.findByRole("button", { name: "Try again" });
    await userEvent.click(dark());
    expect(dark().checked).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("Synthetic workspace unavailable");
  });
});
