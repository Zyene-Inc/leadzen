import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import LeadDetail from "@/components/lead-detail";
import Inbox from "@/components/inbox";
import DiscoveryLive from "@/components/discovery-live";
import { api } from "@/lib/client-api";
import { useWorkspaceContext } from "@/lib/workspace-context";
import { lead, user } from "./fixtures";

vi.mock("@/lib/workspace-context", () => ({
  useWorkspaceContext: vi.fn(), recordWorkspaceContext: vi.fn(async () => {}),
  flushWorkspaceContext: vi.fn(async () => {}),
}));
const call = vi.mocked(api);
const context = vi.mocked(useWorkspaceContext);
afterEach(() => vi.useRealTimers());

test("a denied contact never records a browser-supplied lead ID", async () => {
  call.mockRejectedValue(new Error("Contact not found"));
  render(<LeadDetail user={user} contactId={9999} />);
  await screen.findByRole("alert");
  expect(context.mock.calls.length).toBeGreaterThan(0);
  expect(context.mock.calls.every(([references]) => references.currentLeadId == null)).toBe(true);
  expect(context.mock.lastCall?.[0].workspacePath).toBe("/contacts");
});

test("a contact reference waits for the authorized API response", async () => {
  let finish!: (value: typeof lead) => void;
  call.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<LeadDetail user={user} contactId={lead.id} />);
  expect(context.mock.lastCall?.[0].currentLeadId).toBeNull();
  await act(async () => finish(lead));
  expect(context.mock.lastCall?.[0]).toMatchObject({ currentLeadId: lead.id, workspacePath: `/contacts/${lead.id}` });
});

test("a denied refresh removes the stale contact and its Chat reference", async () => {
  const running = { ...lead, lookup: { run_id: "synthetic", status: "running", credits_used: null, synthetic: true } };
  call.mockResolvedValueOnce(running).mockRejectedValue(new Error("Contact not found"));
  vi.useFakeTimers();
  await act(async () => { render(<LeadDetail user={user} contactId={lead.id} />); });
  expect(screen.getByRole("heading", { name: lead.name })).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
  expect(screen.queryByRole("heading", { name: lead.name })).toBeNull();
  expect(context.mock.lastCall?.[0].currentLeadId).toBeNull();
});

test("a denied Inbox URL never records its requested conversation ID", async () => {
  call.mockImplementation(async path => {
    if (path === "inbox/conversations/9999") throw new Error("Conversation not found");
    return { items: [], total: 0, limit: 50, offset: 0 };
  });
  render(<Inbox user={user} initialThreadId={9999} />);
  await screen.findByText("Conversation not found");
  expect(context.mock.calls.every(([references]) => references.currentThreadId == null)).toBe(true);
});

test("a denied discovery URL never records its requested run ID", async () => {
  call.mockRejectedValue(new Error("Discovery not found"));
  render(<DiscoveryLive user={user} runId="foreign-synthetic-run" />);
  await screen.findByText("Discovery not found");
  expect(context.mock.calls.every(([references]) => references.currentRunId == null)).toBe(true);
});
