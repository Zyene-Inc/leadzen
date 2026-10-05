import { test, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { Autopilot } from "@/components/autopilot";
const call = vi.mocked(api);
const setup = { revision: "revision1", blockers: [], target: "Restaurants in New York", product: "Our saved offer", sender: "sender@example.com", signature: "Sender", booking_link: "", service_enabled: false };
const scope = { timezone: "America/New_York", daily_contacts: 10, monthly_contacts: 200, daily_credits: 10, monthly_credits: 200, daily_ai_requests: 60, monthly_ai_requests: 1200, authorization_days: 30, followup_days: [3, 5], tone: "Brief" };
const policy = { id: "p1", enabled: true, scope, expires_at: "2026-11-01T15:00:00Z", next_start: "2026-10-05T14:00:00Z", heartbeat_at: null, issue: "", setup_changed: false };
const writes = () => call.mock.calls.filter(([, init]) => init?.method === "POST");

test("switch opens review without side effects, Escape cancels", async () => {
  call.mockResolvedValue({ setup, policy: null, runs: [] });
  render(<Autopilot />);
  const toggle = await screen.findByRole("switch", { name: "Daily Autopilot" });
  await waitFor(() => expect((toggle as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(toggle);
  expect(screen.getByText("Restaurants in New York")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Enable automatic outreach" }) as HTMLButtonElement).disabled).toBe(true);
  expect(writes()).toHaveLength(0);
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("heading", { name: "Set up daily outreach" })).toBeNull();
  expect(document.activeElement).toBe(toggle);
});

test("explicit approval sends exact scope once, with followups off", async () => {
  call.mockResolvedValue({ setup, policy: null, runs: [] });
  render(<Autopilot />);
  await waitFor(() => expect((screen.getByRole("switch") as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole("switch"));
  await userEvent.click(screen.getByRole("checkbox", { name: "Add follow-ups" }));
  await userEvent.click(screen.getByRole("checkbox", { name: /I authorize recurring/ }));
  const submit = screen.getByRole("button", { name: "Enable automatic outreach" });
  fireEvent.click(submit); fireEvent.click(submit);
  await waitFor(() => expect(writes()).toHaveLength(1));
  const body = JSON.parse(String(writes()[0][1]?.body));
  expect(body.authorize_automatic_outreach).toBe(true);
  expect(body.followup_days).toEqual([]);
  expect(body.revision).toBe("revision1");
  expect(body.daily_contacts).toBe(10);
  expect(body.timezone).toBe("America/New_York");
  expect(body.sending_schedule).toEqual({ timezone: "America/New_York", days: [0, 1, 2, 3, 4], start: "08:00", end: "20:00" });
});

test("Off writes immediately without another permission step", async () => {
  call.mockResolvedValue({ setup, policy, runs: [] });
  render(<Autopilot />);
  await waitFor(() => expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true"));
  fireEvent.click(screen.getByRole("switch")); fireEvent.click(screen.getByRole("switch"));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ enabled: false });
});

test("failed enable keeps the form and approval visible", async () => {
  call.mockImplementation(async (_path, init) => { if (init?.method) throw new Error("Setup changed. Review again."); return { setup, policy: null, runs: [] }; });
  render(<Autopilot />);
  await waitFor(() => expect((screen.getByRole("switch") as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole("switch"));
  await userEvent.click(screen.getByRole("checkbox", { name: /I authorize recurring/ }));
  await userEvent.click(screen.getByRole("button", { name: "Enable automatic outreach" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Setup changed");
  expect(screen.getByRole("heading", { name: "Set up daily outreach" })).toBeTruthy();
});

test("a saved one-follow-up authorization can be reviewed and edited without adding another", async () => {
  call.mockResolvedValue({ setup, policy: { ...policy, enabled: false, scope: { ...scope, followup_days: [3] } }, runs: [] });
  render(<Autopilot />);
  await waitFor(() => expect((screen.getByRole("switch") as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole("switch"));
  const delay = screen.getByRole("spinbutton", { name: "Follow-up 1: sending days after previous email" });
  expect(screen.queryByRole("spinbutton", { name: /Follow-up 2/ })).toBeNull();
  await userEvent.clear(delay);
  await userEvent.type(delay, "4");
  await userEvent.click(screen.getByRole("checkbox", { name: /I authorize recurring/ }));
  await userEvent.click(screen.getByRole("button", { name: "Enable automatic outreach" }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(JSON.parse(String(writes()[0][1]?.body)).followup_days).toEqual([4]);
});

test.each([
  ["2026-10-05T14:00:00Z", "Oct 5, 2026, 10:00 AM"],
  ["2026-11-02T15:00:00Z", "Nov 2, 2026, 10:00 AM"],
])("next start %s is shown in New York time across daylight saving changes", async (nextStart, expected) => {
  call.mockResolvedValue({ setup, policy: { ...policy, next_start: nextStart, scope: { ...scope, timezone: "Asia/Kolkata" } }, runs: [] });
  render(<Autopilot />);
  expect((await screen.findByText(/Next scheduled start/)).textContent).toBe(`Next scheduled start: ${expected} · New York (Eastern Time)`);
});

test("authorization expiry uses the New York date rather than a UTC slice", async () => {
  call.mockResolvedValue({ setup, policy: { ...policy, expires_on: "2026-11-01", expires_at: "2026-11-01T01:00:00Z" }, runs: [] });
  render(<Autopilot />);
  expect((await screen.findByText(/authorization ends/)).textContent).toContain("authorization ends Oct 31, 2026");
});
