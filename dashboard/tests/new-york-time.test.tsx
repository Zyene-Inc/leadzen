import { afterEach, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Activity } from "@/components/activity-feed";
import { ApprovalCard } from "@/components/chat-results";
import { ChatHistory } from "@/components/chat-history";
import { DiscoveryActivityItem } from "@/components/discovery-activity";
import { LeadTimeline } from "@/components/lead-timeline";
import { api } from "@/lib/client-api";
import { activityTime } from "@/lib/activity";
import { formatNewYorkDateTime, LEADZEN_TIME_ZONE, newYorkDayKey, newYorkHour } from "@/lib/date-time";
import { formatTimelineDate } from "@/lib/leads";
import { sentTime } from "@/lib/outreach";
import { lead, user } from "./fixtures";

afterEach(() => { vi.useRealTimers(); });

test("date formatting always uses New York, including a caller's conflicting timezone", () => {
  expect(LEADZEN_TIME_ZONE).toBe("America/New_York");
  const at = "2026-10-03T01:30:00Z";
  expect(formatNewYorkDateTime(at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "Asia/Tokyo" })).toBe("Oct 2, 9:30 PM");
  expect(sentTime(at)).toBe("Oct 2, 9:30 PM");
  expect(formatTimelineDate(at)).toEqual({ date: "Oct 2, 2026", time: "Oct 2, 2026, 9:30 PM (America/New_York)" });
  expect(formatTimelineDate(null)).toEqual({ date: "Date pending", time: "" });
});

test.each([
  ["2026-01-03T14:15:00Z", "09:15", 9],
  ["2026-07-03T14:15:00Z", "10:15", 10],
  ["2026-03-08T06:59:00Z", "01:59", 1],
  ["2026-03-08T07:00:00Z", "03:00", 3],
  ["2026-11-01T05:30:00Z", "01:30", 1],
  ["2026-11-01T06:30:00Z", "01:30", 1],
  ["2026-10-03T04:00:00Z", "00:00", 0],
])("timestamps and greeting clocks honor Eastern daylight saving at %s", (at, clock, hour) => {
  expect(activityTime(at).clock).toBe(clock);
  expect(newYorkHour(at)).toBe(hour);
});

test("New York calendar grouping handles UTC midnight and short/long DST days", () => {
  expect(newYorkDayKey("2026-10-03T01:00:00Z")).toBe("2026-10-02");
  expect(newYorkDayKey("2026-03-09T04:30:00Z", -1)).toBe("2026-03-08");
  expect(newYorkDayKey("2026-11-02T05:30:00Z", -1)).toBe("2026-11-01");
});

test("Activity groups by New York Today/Yesterday even after UTC has changed dates", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-03T01:00:00Z"));
  vi.mocked(api).mockResolvedValue({ limit: 100, items: [
    { id: "a", at: "2026-10-03T00:30:00Z", title: "This evening", detail: "", kind: "info", href: null },
    { id: "b", at: "2026-10-02T01:00:00Z", title: "Previous evening", detail: "", kind: "info", href: null },
  ] });
  render(<Activity user={user} />);
  const today = await screen.findByRole("region", { name: "Today" });
  expect(within(today).getByText("This evening")).toBeTruthy();
  expect(within(today).getByText("20:30")).toBeTruthy();
  expect(within(screen.getByRole("region", { name: "Yesterday" })).getByText("Previous evening")).toBeTruthy();
  expect(screen.getByText(/saved events · New York \(Eastern Time\)/)).toBeTruthy();
});

test("Chat history shows Eastern dates and groups calendar days at the seven-day boundary", () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-03T01:00:00Z"));
  render(<ChatHistory items={[
    { id: "recent", title: "Recent chat", updated_at: "2026-09-27T01:00:00Z" },
    { id: "week", title: "Seven days ago", updated_at: "2026-09-26T01:00:00Z" },
  ]} />);
  const recent = screen.getByRole("link", { name: /Recent chat/ });
  const week = screen.getByRole("link", { name: /Seven days ago/ });
  expect(recent.querySelector("time")?.textContent).toBe("Sep 26");
  expect(week.querySelector("time")?.textContent).toBe("Sep 25");
  expect(recent.closest("section")?.querySelector("h2")?.textContent).toBe("Last 7 days");
  expect(week.closest("section")?.querySelector("h2")?.textContent).toBe("Last 30 days");
});

test("Discovery activity renders canonical timestamps instead of a cached clock from another timezone", () => {
  render(<ol><DiscoveryActivityItem event={{ id: 1, kind: "searching", data: {}, created_at: "2026-10-03T01:30:00Z", display_time: "10:30 AM" }} /></ol>);
  expect(screen.getByText("09:30 PM")).toBeTruthy();
  expect(screen.queryByText("10:30 AM")).toBeNull();
});

test("lead history uses New York without a sequence and preserves the canonical instant", () => {
  const at = "2026-10-03T01:30:00Z";
  const { container } = render(<LeadTimeline lead={{ ...lead, timeline: {
    events: [{ id: "event", label: "Email accepted", status: "accepted", at, subject: "Hello" }],
    sequences: [], history_truncated: false, blocked_reason: "", can_stop: false, suppression: null,
  } }} load={vi.fn()} />);
  expect(container.querySelector("time")?.getAttribute("dateTime")).toBe(at);
  expect(container.querySelector("time")?.textContent).toBe("Oct 2, 2026");
  expect(container.querySelector("time")?.title).toContain("9:30 PM (America/New_York)");
  expect(screen.getByText(/Recorded event dates use New York \(Eastern Time\)/)).toBeTruthy();
});

test("Chat approval expiry uses Eastern time without triggering an action", () => {
  const approve = vi.fn();
  render(<ApprovalCard approval={{ id: "a", tool: "send_email", summary: "Send this message", credits: 0, emails: 1, preview: {} }} expiresAt="2026-10-03T01:30:00Z" busy={false} onApprove={approve} />);
  expect(screen.getByText(/9:30 PM/)).toBeTruthy();
  expect(approve).not.toHaveBeenCalled();
});
