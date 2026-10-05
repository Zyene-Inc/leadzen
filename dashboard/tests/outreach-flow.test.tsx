import { test, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { InboxCheck } from "@/components/inbox-check";
import { NeedsAttention } from "@/components/needs-attention";
import { OutreachComposer } from "@/components/outreach-composer";
import Campaigns from "@/components/campaigns";
import { lead, user } from "./fixtures";

const call = vi.mocked(api);
const run = { id: "run1", status: "awaiting_approval", approval: { id: "approval1", preview: { from_address: "sender@example.com" } } };
const writes = () => call.mock.calls.filter(([, init]) => !!init?.method);

test("inbox checks require inline approval, show cost and mailbox, and Cancel is inert", async () => {
  call.mockImplementation(async (path) => path === "inbox/check" ? { thread_id: "thread1", run } : { ...run, status: "cancelled", approval: null });
  render(<InboxCheck refreshed={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Check for replies" }));
  await screen.findByRole("heading", { name: "Check your connected inbox?" });
  expect(screen.getByText(/sender@example.com/).textContent).toContain("AI charges may apply");
  expect(writes()).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(JSON.parse(String(writes()[1][1]?.body))).toEqual({ action_id: "approval1", approved: false });
  expect(screen.queryByRole("button", { name: "Approve & check replies" })).toBeNull();
});

test("inbox approve blocks double submissions and uses only the server action id", async () => {
  call.mockImplementation(async (path) => path === "inbox/check" ? { thread_id: "thread1", run } : { ...run, status: "queued", approval: null });
  render(<InboxCheck refreshed={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Check for replies" }));
  const confirm = await screen.findByRole("button", { name: "Approve & check replies" });
  fireEvent.click(confirm); fireEvent.click(confirm);
  await waitFor(() => expect(writes()).toHaveLength(2));
  expect(writes()[1][0]).toBe("chat/runs/run1/approval");
  expect(JSON.parse(String(writes()[1][1]?.body))).toEqual({ action_id: "approval1", approved: true });
  expect((await screen.findByRole("button", { name: "Checking replies…" }) as HTMLButtonElement).disabled).toBe(true);
});

test("attention is read only and routes to the saved record", async () => {
  call.mockResolvedValue({ items: [{ id: "draft1", label: "Dental outreach", detail: "Draft ready", href: "/outreach?campaign=campaign1" }] });
  render(<NeedsAttention />);
  expect((await screen.findByRole("link", { name: /Dental outreach/ })).getAttribute("href")).toBe("/outreach?campaign=campaign1");
  expect(writes()).toHaveLength(0);
});

test("AI preparation preserves exact selection and requests draft-only work", async () => {
  call.mockImplementation(async (path) => {
    if (path.startsWith("leads")) return { items: [lead], total: 1, limit: 50 };
    if (path === "chat/threads") return { id: "thread1" };
    if (path.endsWith("/messages")) return { run: { id: "run1" } };
    return { messages: [], run: { id: "run1", status: "queued" } };
  });
  render(<OutreachComposer actorId={1} initialSelection={[1]} aiReady close={vi.fn()} saved={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Prepare drafts" }));
  await screen.findByRole("heading", { name: "Preparing your draft" });
  const request = JSON.parse(String(writes()[1][1]?.body));
  expect(request.context.selectedLeadIds).toEqual([1]);
  expect(request.content).toContain("Do not send, activate, sync a mailbox, discover leads or buy emails");
  expect(writes().some(([path]) => path.includes("/run") || path.includes("approval"))).toBe(false);
});

test("changing selections after a preparation failure creates a new request identity", async () => {
  call.mockImplementation(async (path) => {
    if (path.startsWith("leads")) return { items: [lead, { ...lead, id: 2, name: "Second lead" }], total: 2, limit: 50 };
    if (path === "chat/threads") return { id: `thread${writes().filter(([p]) => p === "chat/threads").length}` };
    throw new Error("Active task must finish");
  });
  render(<OutreachComposer actorId={1} initialSelection={[1]} aiReady close={vi.fn()} saved={vi.fn()} />);
  await screen.findByRole("checkbox", { name: /Second lead/ });
  await userEvent.click(screen.getByRole("button", { name: "Prepare drafts" }));
  await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("checkbox", { name: /Second lead/ }));
  await userEvent.click(screen.getByRole("button", { name: "Prepare drafts" }));
  await waitFor(() => expect(writes().filter(([p]) => p.endsWith("/messages"))).toHaveLength(2));
  const requests = writes().filter(([p]) => p.endsWith("/messages")).map(([, init]) => JSON.parse(String(init?.body)));
  expect(requests[0].request_id).not.toBe(requests[1].request_id);
  expect(requests[1].context.selectedLeadIds).toEqual([1, 2]);
});

test("an unfinished inbox approval is restored after mounting without another check", async () => {
  call.mockResolvedValue({ check: { thread_id: "thread1", run } });
  render(<InboxCheck refreshed={vi.fn()} />);
  await screen.findByRole("button", { name: "Approve & check replies" });
  expect(writes()).toHaveLength(0);
});

test("save for later persists a draft and never activates or sends", async () => {
  const existing = { id: "campaign1", name: "Saved outreach", category: "outreach", status: "draft", automatic_followups: false, steps: [{ subject: "Hello", body: "Draft copy", delay_days: 0 }], total: 1, sent: 0, from_address: "sender@example.com", target: "", product: "", booking_link: "", signature: "", delay_basis: "working_days", delay_timezone: "UTC", recipients: [{ id: 1, email: "bruce@example.com", status: "pending", next_step: 0, next_send_at: null }] };
  call.mockImplementation(async (_, init) => init?.method ? existing : { items: [lead], total: 1, limit: 50 });
  const close = vi.fn();
  render(<OutreachComposer actorId={1} initialSelection={[]} existing={existing} aiReady close={close} saved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Updated subject" } });
  await userEvent.click(screen.getByRole("button", { name: "Save for later" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(writes()).toHaveLength(1);
  expect(writes()[0][0]).toBe("campaigns/campaign1");
  expect(JSON.parse(String(writes()[0][1]?.body)).steps[0].subject).toBe("Updated subject");
});

test("an archived Autopilot deep link reveals its saved messages without changing the default open filter", async () => {
  const archived = { id: "archived-autopilot", name: "Archived daily outreach", category: "outreach", status: "archived", autopilot: true, automatic_followups: false, steps: [], total: 1, sent: 1, from_address: "sender@example.com", target: "Owners", product: "Product", booking_link: "", signature: "", delay_basis: "working_days", delay_timezone: "UTC", recipients: [{ id: 1, email: lead.email, status: "stopped", next_step: 1, next_send_at: null, personal_steps: [{ subject: "Archived personal message", body: "Saved personal copy", delay_days: 0 }] }] };
  call.mockImplementation(async (path) => {
    if (path === "autopilot") return { setup: { revision: "r", blockers: [], target: "Owners", product: "Product", sender: "sender@example.com", signature: "", booking_link: "", service_enabled: false }, policy: null, runs: [] };
    if (path === "outreach") return { reviews: [], window: { start: 8, end: 20, timezone: "UTC" } };
    return { items: path === "campaigns" ? [archived] : [] };
  });
  const ordinary = render(<Campaigns user={user} />);
  await screen.findByRole("heading", { name: "Start a conversation" });
  expect(screen.getByRole("button", { name: "Open" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.queryByRole("heading", { name: archived.name })).toBeNull();
  ordinary.unmount();

  render(<Campaigns user={user} initialCampaignId={archived.id} />);
  await screen.findByRole("heading", { name: archived.name });
  expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText("Saved personal copy").closest("details")?.open).toBe(true);
  expect(writes()).toHaveLength(0);
  expect(call.mock.calls.some(([path]) => path.includes("/preview"))).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(screen.queryByRole("heading", { name: archived.name })).toBeNull();
});
