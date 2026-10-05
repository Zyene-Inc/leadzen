import { test, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import SettingsPage from "@/components/settings";
import { SettingsEditor } from "@/components/settings-editor";
import Outreach from "@/components/campaigns";
import CampaignSendReview from "@/components/campaign-send-review";
import { Autopilot } from "@/components/autopilot";
import { LeadTimeline } from "@/components/lead-timeline";
import { defaultSendingSchedule, normalizeSendingSchedule, scheduleDayLabel, scheduleError, scheduleHours, scheduleSummary, windowSchedule } from "@/lib/sending-schedule";
import { user, settings, lead } from "./fixtures";

const call = vi.mocked(api);
const writes = () => call.mock.calls.filter(([, init]) => !!init?.method);
const customSchedule = { days: [0, 2, 5], start: "09:30", end: "16:45", timezone: "America/New_York" };
const customWindow = { days: customSchedule.days, start_time: customSchedule.start, end_time: customSchedule.end, start: 9.5, end: 16.75, timezone: customSchedule.timezone, weekdays_only: false };
const customSettings = { ...settings, workspace: { ...settings.workspace, sending_schedule: customSchedule } };
const customSetup = { revision: "schedule-revision", blockers: [], target: "Practice owners", product: "Offer", sender: "sender@example.com", signature: "Sender", booking_link: "", service_enabled: false, sending_schedule: customSchedule };

test("Settings shows selected days and minutes in fixed New York time without writes", async () => {
  call.mockResolvedValue({ ...customSettings, workspace: { ...customSettings.workspace, sending_schedule: { ...customSchedule, timezone: "Asia/Kolkata" } } });
  render(<SettingsPage user={user} />);
  const button = await screen.findByRole("button", { name: "Edit Sending hours" });
  expect(screen.getByText("9:30 AM–4:45 PM")).toBeTruthy();
  expect(screen.getByText("Mon, Wed, Sat · New York (Eastern Time)")).toBeTruthy();
  expect(screen.queryByText(/Asia\/Kolkata/)).toBeNull();
  await userEvent.click(button);
  expect((screen.getByRole("checkbox", { name: "Saturday" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByLabelText("Start time") as HTMLInputElement).value).toBe("09:30");
  expect(writes()).toHaveLength(0);
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(document.activeElement).toBe(button);
});

test("selected days and HH:MM times save one normalized workspace setting without automatic requests", async () => {
  call.mockResolvedValue(customSettings);
  const saved = vi.fn();
  render(<SettingsEditor section="schedule" data={settings} saved={saved} cancel={vi.fn()} onBusy={vi.fn()} />);
  await userEvent.click(screen.getByRole("checkbox", { name: "Tuesday" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Thursday" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Friday" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Saturday" }));
  fireEvent.change(screen.getByLabelText("Start time"), { target: { value: "09:30" } });
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: "16:45" } });
  const submit = screen.getByRole("button", { name: "Save changes" });
  fireEvent.click(submit); fireEvent.click(submit);
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(writes()).toHaveLength(1);
  expect(writes()[0][0]).toBe("settings");
  expect(writes()[0][1]?.method).toBe("PUT");
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ workspace_updates: { sending_schedule: customSchedule } });
});

test("weekly shortcuts select real days and Escape discards the unsaved copy", async () => {
  call.mockResolvedValue(settings);
  render(<SettingsPage user={user} />);
  const edit = await screen.findByRole("button", { name: "Edit Sending hours" });
  await userEvent.click(edit);
  await userEvent.click(screen.getByRole("button", { name: "Every day" }));
  expect(screen.getAllByRole("checkbox").every((checkbox) => (checkbox as HTMLInputElement).checked)).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Weekdays" }));
  expect((screen.getByRole("checkbox", { name: "Sunday" }) as HTMLInputElement).checked).toBe(false);
  fireEvent.change(screen.getByLabelText("Start time"), { target: { value: "11:15" } });
  await userEvent.keyboard("{Escape}");
  expect(document.activeElement).toBe(edit);
  await userEvent.click(edit);
  expect((screen.getByLabelText("Start time") as HTMLInputElement).value).toBe("08:00");
  expect(writes()).toHaveLength(0);
});

test("at least one day is required before saving", async () => {
  call.mockResolvedValue(settings);
  render(<SettingsEditor section="schedule" data={settings} saved={vi.fn()} cancel={vi.fn()} onBusy={vi.fn()} />);
  for (const day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]) await userEvent.click(screen.getByRole("checkbox", { name: day }));
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(screen.getByRole("alert").textContent).toContain("Choose at least one sending day");
  expect(writes()).toHaveLength(0);
});

test.each(["08:00", "07:30"])("end time %s cannot be at or before start time", async (end) => {
  call.mockResolvedValue(settings);
  render(<SettingsEditor section="schedule" data={settings} saved={vi.fn()} cancel={vi.fn()} onBusy={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: end } });
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(screen.getByRole("alert").textContent).toContain("End time must be later");
  expect(writes()).toHaveLength(0);
});

test("New York time is read-only and stale timezone settings save only New York", async () => {
  call.mockResolvedValue(customSettings);
  render(<SettingsEditor section="schedule" data={{ ...customSettings, workspace: { ...customSettings.workspace, sending_schedule: { ...customSchedule, timezone: "Asia/Kolkata" } } }} saved={vi.fn()} cancel={vi.fn()} onBusy={vi.fn()} />);
  expect(screen.queryByLabelText("Timezone")).toBeNull();
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByText("New York (Eastern Time)")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Help: New York time" }));
  expect(screen.getByRole("tooltip").textContent).toContain("Daylight saving time adjusts automatically");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ workspace_updates: { sending_schedule: customSchedule } });
});

test("server schedule rejection preserves the edited schedule and reports its error", async () => {
  call.mockRejectedValue(new Error("This schedule is unavailable. Review it again."));
  const cancel = vi.fn(), saved = vi.fn();
  render(<SettingsEditor section="schedule" data={customSettings} saved={saved} cancel={cancel} onBusy={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Review it again");
  expect((screen.getByLabelText("Start time") as HTMLInputElement).value).toBe("09:30");
  expect(saved).not.toHaveBeenCalled();
  expect(cancel).not.toHaveBeenCalled();
  expect(writes()).toHaveLength(1);
});

test("Autopilot review uses the server's Settings snapshot instead of its old authorization timezone", async () => {
  call.mockResolvedValue({ setup: { ...customSetup, sending_schedule: { ...customSchedule, timezone: "Asia/Kolkata" } }, policy: { enabled: false, scope: { timezone: "Europe/London", sending_schedule: settings.workspace.sending_schedule } }, runs: [] });
  render(<Autopilot />);
  await waitFor(() => expect((screen.getByRole("switch") as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole("switch"));
  expect(screen.getByText(/Discovery starts at 9:30 AM/).textContent).toContain("Mon, Wed, Sat");
  expect(screen.getByText(/Discovery starts at 9:30 AM/).textContent).toContain("New York (Eastern Time)");
  expect(screen.queryByText(/Asia\/Kolkata|Europe\/London/)).toBeNull();
  expect(screen.queryByLabelText("Timezone")).toBeNull();
  expect(screen.getByRole("link", { name: "Edit schedule in Settings" }).getAttribute("href")).toBe("/settings#sending-hours");
  await userEvent.click(screen.getByRole("checkbox", { name: /I authorize recurring/ }));
  await userEvent.click(screen.getByRole("button", { name: "Enable automatic outreach" }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  const body = JSON.parse(String(writes()[0][1]?.body));
  expect(body.timezone).toBe("America/New_York");
  expect(body.sending_schedule).toEqual(customSchedule);
  expect(body.revision).toBe("schedule-revision");
});

test("an enabled legacy Autopilot keeps its original 10 AM start label", async () => {
  call.mockResolvedValue({ setup: customSetup, policy: { enabled: true, scope: { timezone: "Asia/Kolkata", daily_contacts: 10, followup_days: [3, 5] }, expires_at: "2026-11-03T14:00:00Z", next_start: null, issue: "" }, runs: [] });
  render(<Autopilot />);
  expect(await screen.findByText("Weekdays · Starts 10 AM · New York (Eastern Time)")).toBeTruthy();
  expect(screen.queryByText(/Starts 9:30 AM/)).toBeNull();
});

test("Outreach summary shows the actual schedule and links to Settings without sending", async () => {
  call.mockImplementation(async (path) => path === "autopilot" ? { setup: customSetup, policy: null, runs: [] } : path === "outreach" ? { eligible: 0, remaining_today: 10, from_address: "sender@example.com", ai_ready: false, window: customWindow, reviews: [] } : { items: [] });
  const { container } = render(<Outreach user={user} />);
  await screen.findByText("9:30 AM–4:45 PM");
  const summary = within(container.querySelector(".outreach-summary")! as HTMLElement);
  expect(summary.getByText("Mon, Wed, Sat · New York (Eastern Time)")).toBeTruthy();
  expect(summary.getByRole("link", { name: "Edit hours" }).getAttribute("href")).toBe("/settings#sending-hours");
  expect(writes()).toHaveLength(0);
});

test("automatic follow-up review shows the exact server schedule before approval", async () => {
  call.mockResolvedValue({ window: customWindow, automatic_window: customWindow, revision: "r1", from_address: "sender@example.com", automatic_available: true, delay_basis: "working_days", timezone: "America/New_York", recipients: [{ id: 1, email: lead.email, subject: "Hello", body: "First message", step: 1, followups: [{ step: 2, subject: "Following up", body: "Second message", delay_days: 3 }] }] });
  render(<CampaignSendReview campaignId="c1" count={1} close={vi.fn()} sent={vi.fn()} />);
  await screen.findByText(/Sending schedule: Mon, Wed, Sat · 9:30 AM–4:45 PM · New York \(Eastern Time\)/);
  await userEvent.click(screen.getByRole("checkbox", { name: "Approve automatic follow-ups for these recipients" }));
  expect(screen.getByText(/Follow-ups use Mon, Wed, Sat/).textContent).toContain("9:30 AM–4:45 PM");
  expect(writes()).toHaveLength(0);
});

test("lead timeline uses its saved sequence sending schedule", () => {
  render(<LeadTimeline lead={{ ...lead, timeline: { events: [], history_truncated: false, blocked_reason: "", can_stop: false, suppression: null, sequences: [{ id: "c1", name: "Personal outreach", status: "pending", campaign_status: "active", timezone: "America/New_York", automatic: true, sending_schedule: customSchedule, steps: [{ id: "s1", label: "Follow-up", status: "estimated", at: null, subject: "Hello" }] }] } }} load={vi.fn()} />);
  expect(screen.getByText(/Approved follow-ups run while/).textContent).toContain("Mon, Wed, Sat · 9:30 AM–4:45 PM · New York (Eastern Time)");
  expect(writes()).toHaveLength(0);
});

test("fractional legacy hours retain minutes and weekday subsets are never mislabeled", () => {
  expect(scheduleHours(windowSchedule({ start: 8, end: 20, timezone: "America/New_York" }))).toBe("8 AM–8 PM");
  expect(scheduleHours(windowSchedule({ start: 8.25, end: 20, timezone: "America/New_York" }))).toBe("8:15 AM–8 PM");
  expect(scheduleDayLabel([4, 0, 2])).toBe("Mon, Wed, Fri");
  expect(scheduleDayLabel([0, 1, 2, 3, 4])).toBe("Weekdays");
  expect(scheduleSummary(windowSchedule(customWindow))).toBe("Mon, Wed, Sat · 9:30 AM–4:45 PM · New York (Eastern Time)");
});

test("schedule helpers always normalize and display New York regardless of stale payload zones", () => {
  const stale = { ...customSchedule, timezone: "Asia/Kolkata" };
  expect(defaultSendingSchedule().timezone).toBe("America/New_York");
  expect(normalizeSendingSchedule(stale)).toEqual(customSchedule);
  expect(windowSchedule({ ...customWindow, timezone: "Europe/London" })).toEqual(customSchedule);
  expect(scheduleSummary(stale)).toBe("Mon, Wed, Sat · 9:30 AM–4:45 PM · New York (Eastern Time)");
  expect(scheduleError(stale)).toContain("must use New York");
});
