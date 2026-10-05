import { afterEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import { ChatDiscoveryCard } from "@/components/chat-discovery-card";
import DiscoveryLive from "@/components/discovery-live";
import { DiscoveryActivityFeed, DiscoveryActivityItem, DiscoveryCandidateList, DiscoveryCandidateRow, DiscoveryCurrentActivity } from "@/components/discovery-activity";
import { candidateWorkspaceLink, currentDiscoveryActivity, recentDiscoveryCandidates, statusLabel, summaryNote, summaryTitle, type Candidate, type DiscoveryEvent } from "@/lib/discovery";
import { api } from "@/lib/client-api";
import { progress, user } from "./fixtures";

const sarah: Candidate = { id: 201, source_id: 801, contact_id: 17, name: "Sarah Johnson", title: "Owner", company: "Bright Smile", reason: "Owns a dental practice in the target region.", email: "", profile_url: "https://www.linkedin.com/in/sarah-example", outcome: "qualified" };
const mark: Candidate = { ...sarah, id: 202, source_id: 802, contact_id: null, name: "Mark Jones", title: "Recruiter", company: "Talent Co", outcome: "rejected", reason: "Recruiting role has no responsibility for a dental practice." };
const event = (id: number, kind: string, candidate: Partial<Candidate> = {}): DiscoveryEvent => ({ id, kind, data: candidate, created_at: `2026-10-03T12:00:${String(id).padStart(2, "0")}Z` });
afterEach(() => { vi.useRealTimers(); });

describe("Discovery UI uses persisted identities and verdicts", () => {
  test.each([
    ["queued", "Waiting"], ["running", "In progress"], ["succeeded", "Complete"],
    ["completed", "Finished"], ["failed", "Needs attention"], ["cancelled", "Stopped"],
    ["stopped", "Stopped"], ["paused", "Paused"],
  ])("%s has a readable label without changing goal counts or status", (status, expected) => {
    const data = { ...progress, status, goal_reached: false };
    expect(statusLabel(data)).toBe(expected);
    expect(data.status).toBe(status);
    expect(data.counts.produced).toBe(1);
    expect(data.goal_reached).toBe(false);
  });

  test("requested safe-checkpoint controls override running labels until the worker stops", () => {
    expect(statusLabel({ ...progress, stop_requested: true })).toBe("Stopping");
    expect(statusLabel({ ...progress, pause_requested: true })).toBe("Pausing");
    expect(statusLabel({ ...progress, status: "cancelled", stop_requested: true })).toBe("Stopped");
    expect(statusLabel({ ...progress, status: "paused", pause_requested: true })).toBe("Paused");
  });

  test("a successfully finished worker with fewer results retains its actual unmet goal", () => {
    const data = { ...progress, status: "succeeded", goal_reached: false };
    expect(summaryTitle(data)).toBe("Discovery finished");
    expect(currentDiscoveryActivity(data)).toBe("Discovery finished");
    expect(summaryNote(data)).toContain("ended before the requested goal");
    expect(data.counts.produced).toBe(1);
    expect(data.goal.count).toBe(3);
    expect(data.goal_reached).toBe(false);
  });

  test("qualified and rejected candidates show the exact recorded reason and canonical links", () => {
    const { container } = render(<><DiscoveryCandidateRow candidate={sarah} /><DiscoveryCandidateRow candidate={mark} /></>);
    expect(screen.getByText(sarah.reason)).toBeTruthy();
    expect(screen.getByText(mark.reason)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open in Workspace →" }).getAttribute("href")).toBe("/contacts/17");
    expect(container.querySelector('[data-outcome="rejected"] a[href^="/contacts"]')).toBeNull();
    expect(candidateWorkspaceLink({ id: 999, source_id: 500, contact_id: null })).toBeNull();
    expect(candidateWorkspaceLink({ contact_id: -1 })).toBeNull();
  });

  test("a returned profile is not presented as qualified or assigned an invented reason", () => {
    render(<DiscoveryCandidateRow candidate={{ ...mark, outcome: "pending", reason: "", contact_id: null }} />);
    expect(screen.getByText("Not evaluated yet")).toBeTruthy();
    expect(screen.queryByText("Why rejected:")).toBeNull();
    expect(screen.queryByText("Qualified")).toBeNull();
    expect(screen.queryByText(/No qualification reason/)).toBeNull();
  });

  test.each(["qualified", "rejected"])("rediscovering an already %s candidate preserves the actual prior verdict", (outcome) => {
    const candidate = { ...sarah, outcome };
    const { rerender } = render(<DiscoveryActivityItem event={event(1, "discovered", candidate)} />);
    expect(screen.getByText(`Returned by the profile search. A ${outcome} verdict was already recorded.`)).toBeTruthy();
    expect(screen.queryByText(/Qualification is still pending/)).toBeNull();
    rerender(<DiscoveryActivityItem event={event(2, "evaluating", candidate)} />);
    expect(screen.getByText(/A new verdict has not been recorded for this check/)).toBeTruthy();
    expect(candidate.outcome).toBe(outcome);
    expect(candidate.reason).toBe(sarah.reason);
  });

  test("current activity uses the real evaluating candidate and stops its active state when paused or finished", () => {
    const current = { ...progress, current_activity: event(1, "evaluating", sarah) };
    const { container, rerender } = render(<DiscoveryCurrentActivity data={current} />);
    expect(screen.getByRole("status").textContent).toBe("Evaluating Sarah Johnson");
    expect(container.querySelector('[data-active="true"]')).toBeTruthy();
    rerender(<DiscoveryCurrentActivity data={{ ...current, status: "paused" }} />);
    expect(screen.getByRole("status").textContent).toBe("Discovery paused");
    expect(container.querySelector('[data-active="true"]')).toBeNull();
    rerender(<DiscoveryCurrentActivity data={{ ...current, status: "failed", goal_reached: true }} />);
    expect(screen.getByRole("status").textContent).toBe("Discovery needs attention");
    expect(currentDiscoveryActivity({ ...current, stop_requested: true })).toContain("Stopping");
  });

  test("only newly arrived events receive the entry motion hook and newest activity is first", () => {
    const first = event(1, "discovered", { ...mark, outcome: "pending" });
    const next = event(2, "rejected", mark);
    const { container, rerender } = render(<DiscoveryActivityFeed events={[first]} />);
    expect(container.querySelector('[data-new="true"]')).toBeNull();
    rerender(<DiscoveryActivityFeed events={[first, next]} />);
    expect(container.querySelector("li")?.getAttribute("data-kind")).toBe("rejected");
    expect(container.querySelectorAll('[data-new="true"]')).toHaveLength(1);
    rerender(<DiscoveryActivityFeed events={[{ ...first }, { ...next }]} />);
    expect(container.querySelector('[data-new="true"]')).toBeNull();
  });

  test("candidate ordering follows actual recent work, while old runs can still use persisted leads", () => {
    const data = { ...progress, candidates: [sarah, mark], events: [event(1, "discovered", mark), event(2, "qualified", sarah)] };
    expect(recentDiscoveryCandidates(data).map((candidate) => candidate.name)).toEqual(["Sarah Johnson", "Mark Jones"]);
    expect(recentDiscoveryCandidates({ ...progress, leads: [sarah] })).toEqual([sarah]);
  });

  test("an actual newly saved verdict triggers candidate motion while a reloaded verdict does not", () => {
    const pending = { ...sarah, outcome: "pending", reason: "", contact_id: null };
    const { container, rerender } = render(<DiscoveryCandidateList candidates={[pending]} />);
    expect(container.querySelector('[data-new="true"]')).toBeNull();
    rerender(<DiscoveryCandidateList candidates={[sarah]} />);
    expect(container.querySelector('[data-outcome="qualified"][data-new="true"]')).toBeTruthy();
    rerender(<DiscoveryCandidateList candidates={[{ ...sarah }]} />);
    expect(container.querySelector('[data-new="true"]')).toBeNull();
  });

  test("Chat exposes rejection reasons, pending verdict count and real candidate names without raw logs", () => {
    render(<ChatDiscoveryCard data={{ ...progress, counts: { ...progress.counts, awaiting_evaluation: 6 }, candidates: [sarah, mark], events: [] }} />);
    const candidates = screen.getByLabelText("Recent discovery candidates");
    expect(within(candidates).getByText("Mark Jones")).toBeTruthy();
    expect(within(candidates).getByText(mark.reason)).toBeTruthy();
    expect(screen.getByText("6 discovered profiles have not received a qualification verdict yet.")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Discovery goal" }).getAttribute("value")).toBe("1");
    expect(screen.queryByText("[DEBUG]")).toBeNull();
  });

  test("pending counts come from the backend subset rather than subtracting unrelated totals", () => {
    const { rerender } = render(<ChatDiscoveryCard data={{ ...progress, counts: { ...progress.counts, discovered: 1, evaluated: 1, awaiting_evaluation: 1 } }} />);
    expect(screen.getByText("1 discovered profile has not received a qualification verdict yet.")).toBeTruthy();
    rerender(<ChatDiscoveryCard data={{ ...progress, counts: { ...progress.counts, discovered: 1, evaluated: 1 } }} />);
    expect(screen.queryByText(/discovered profiles? (?:has|have) not received/)).toBeNull();
  });

  test("profile links with credentials are discarded and a missing verdict reason stays unknown", () => {
    render(<DiscoveryActivityItem event={event(1, "rejected", { ...mark, reason: "", profile_url: "https://secret:password@example.com/profile" })} />);
    expect(screen.getByText("No qualification reason was recorded.")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  test("a temporary progress failure preserves the last saved state and automatically reconnects", async () => {
    vi.useFakeTimers();
    const call = vi.mocked(api);
    call.mockResolvedValueOnce({ ...progress, events: [event(1, "evaluating", sarah)] })
      .mockRejectedValueOnce(new Error("Connection interrupted"))
      .mockResolvedValueOnce({ ...progress, status: "completed", goal_reached: true, events: [event(2, "qualified", sarah)], leads: [sarah] });
    render(<DiscoveryLive user={user} runId="run1" />);
    await act(async () => {});
    expect(screen.getByRole("status").textContent).toBe("Evaluating Sarah Johnson");
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByRole("alert").textContent).toContain("Connection interrupted");
    expect(screen.getByRole("status").textContent).toBe("Evaluating Sarah Johnson");
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Discovery Complete");
    expect(call).toHaveBeenCalledTimes(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(call).toHaveBeenCalledTimes(3);
  });
});
