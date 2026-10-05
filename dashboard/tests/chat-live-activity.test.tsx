import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatLiveActivity } from "@/components/chat-live-activity";
import type { Conversation } from "@/lib/chat";
import { progress } from "./fixtures";

const started = "2026-10-03T12:00:00Z";
function conversation(): Conversation {
  return {
    id: "thread", title: "Find leads", updated_at: started,
    run: { id: "run1", status: "running", created_at: started, finished_at: null, discovery_id: progress.id, steps: 1, cancel_requested: false, approval: null, approval_expires_at: null },
    discovery: { ...progress, events: [{ id: 1, kind: "qualified", data: { name: "Sample owner", reason: "Matches the saved target" }, created_at: started }] },
    messages: [
      { id: "user", role: "user", content: "Find leads", data: {}, created_at: started },
      { id: "tool", role: "tool", content: "Searching saved target", data: { tool: "find_leads", result: { status: "running" } }, created_at: started },
    ],
  };
}
afterEach(() => vi.useRealTimers());
function expand(container: HTMLElement) {
  const details = container.querySelector("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
}

describe("Chat live activity", () => {
  it("starts compact, reveals only recorded activity and keeps Workspace links available", () => {
    const { container } = render(<ChatLiveActivity conversation={conversation()} />);
    expect(container.querySelector("details")?.open).toBe(false);
    expect(screen.queryByText("Matches the saved target")).toBeNull();
    expect(screen.getByText("10 profiles found · 1 / 3 qualified leads · 4 evaluated")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open live discovery →" }).getAttribute("href")).toBe("/find-leads/run1");
    expand(container);
    expect(screen.getByText("Matches the saved target")).toBeTruthy();
    expect(screen.getByText("Searching saved target")).toBeTruthy();
  });
  it("ticks once per second from server time and uses the saved end time after completion", () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-03T12:00:12Z"));
    const data = conversation();
    const { rerender } = render(<ChatLiveActivity conversation={data} />);
    expect(screen.getByText("12s")).toBeTruthy();
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByText("14s")).toBeTruthy();
    rerender(<ChatLiveActivity conversation={{ ...data, run: { ...data.run!, status: "succeeded", finished_at: "2026-10-03T12:00:13Z" } }} />);
    expect(screen.getByText("Task complete")).toBeTruthy();
    expect(screen.getByText("13s")).toBeTruthy();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("13s")).toBeTruthy();
    expect(document.querySelector(".chat-work-motion")).toBeNull();
  });
  it.each(["awaiting_approval", "paused", "failed", "cancelled"])("does not animate or tick in %s", status => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-03T12:00:12Z"));
    const data = conversation();
    const { rerender } = render(<ChatLiveActivity conversation={data} />);
    rerender(<ChatLiveActivity conversation={{ ...data, run: { ...data.run!, status } }} />);
    expect(document.querySelector(".chat-work-motion")).toBeNull();
    expect(document.querySelector(".chat-live-elapsed")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("never borrows counts or links from a different discovery run", () => {
    const data = conversation();
    render(<ChatLiveActivity conversation={{ ...data, run: { ...data.run!, discovery_id: "new-run" } }} />);
    expect(screen.queryByText(/10 profiles found/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Open leads →" })).toBeNull();
    expect(screen.getByText("Searching saved target")).toBeTruthy();
  });
  it("restores the current discovery counts from saved history without a live snapshot", () => {
    const data = conversation();
    data.messages[1].data.result = { status: "completed", discovery: data.discovery };
    data.discovery = undefined;
    data.run!.status = "succeeded";
    render(<ChatLiveActivity conversation={data} />);
    expect(screen.getByText("10 profiles found · 1 / 3 qualified leads · 4 evaluated")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View saved results →" }).getAttribute("href")).toBe("/find-leads/run1");
  });
  it("resets expansion for a new request and handles older runs without timing metadata", () => {
    const data = conversation();
    const { container, rerender } = render(<ChatLiveActivity conversation={data} />);
    expand(container);
    rerender(<ChatLiveActivity conversation={{ ...data, run: { ...data.run!, id: "new-run", created_at: undefined } }} />);
    expect(container.querySelector("details")?.open).toBe(false);
    expect(document.querySelector(".chat-live-elapsed")).toBeNull();
  });
  it("does not count failures or interrupted actions as completed", () => {
    const data = conversation();
    data.discovery = undefined;
    data.messages[1].data.result = { error: "Unavailable", status: "failed" };
    const { container } = render(<ChatLiveActivity conversation={data} />);
    expect(screen.queryByText("1 action completed")).toBeNull();
    expand(container);
    expect(screen.getByText("Needs attention")).toBeTruthy();
  });
});
