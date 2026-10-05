import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { recordWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import Campaigns from "@/components/campaigns";
import Contacts from "@/components/contacts";
import Inbox from "@/components/inbox";
import { user, lead } from "./fixtures";
import type { EmailReview, OutreachSetup } from "@/lib/outreach";

vi.mock("@/lib/workspace-context", () => ({ useWorkspaceContext: vi.fn(), recordWorkspaceContext: vi.fn(async () => {}), flushWorkspaceContext: vi.fn(async () => {}) }));
const call = vi.mocked(api);
const context = vi.mocked(useWorkspaceContext);
const setup: OutreachSetup = { eligible: 5, remaining_today: 5, from_address: "sender@example.com", ai_ready: true, next_send_at: null, window: { start: 8, end: 20, timezone: "America/New_York", weekdays_only: true }, reviews: [] };
const review: EmailReview = { actor_id: user.id, id: "saved-review", kind: "initial", status: "draft", from_address: setup.from_address, requested_count: 1, accepted: 0, revision: "r1", stale: false, note: "Not sent", drafts: [{ id: "active-draft", name: lead.name, to: lead.email, subject: "Hello", body: "Saved copy", preview_body: "Saved copy", revision: "d1", approved: false, state: "pending", accepted_at: null }] };

for (let repetition = 1; repetition <= 10; repetition++) describe(`Fresh user journeys pass ${repetition}`, () => {
  test("a recovered lead search clears its obsolete loading error", async () => {
    call.mockRejectedValueOnce(new Error("Temporary list outage")).mockResolvedValue({ items: [lead], total: 1 });
    render(<Contacts user={user} />);
    await screen.findByText("Temporary list outage");
    fireEvent.change(screen.getByLabelText("Search leads"), { target: { value: "Bruce" } });
    await screen.findByRole("link", { name: "View Bruce" });
    expect(screen.queryByText("Temporary list outage")).toBeNull();
  });
  test("closing a saved draft removes its active Chat reference", async () => {
    call.mockImplementation(async path => {
      if (path === "outreach") return setup;
      if (path.startsWith("outreach/reviews/")) return review;
      if (path === "autopilot") return { setup: { revision: "r1", blockers: [], target: "Owners", product: "Product", sender: setup.from_address, signature: "", booking_link: "", service_enabled: false }, policy: null, runs: [] };
      return { items: [] };
    });
    render(<Campaigns user={user} initialReviewId={review.id} />);
    await screen.findByText("Saved copy");
    await userEvent.click(screen.getByRole("button", { name: "Back to outreach" }));
    await screen.findByRole("button", { name: "New outreach" });
    await waitFor(() => expect(context.mock.lastCall?.[0]).toMatchObject({ workspacePath: "/outreach", currentDraftId: null }));
  });
  test("a reply draft keeps its existing Inbox conversation as Workspace context", async () => {
    const conversation = { id: 4, name: "Bruce", address: lead.email, can_reply: true, reply_blocker: "", total_messages: 0, messages: [] };
    call.mockImplementation(async path => path === "outreach/reviews" || path.startsWith("outreach/reviews/") ? { ...review, kind: "reply", thread_id: 4 } : path === "inbox/conversations/4" ? conversation : { items: [], total: 0, limit: 50, offset: 0 });
    render(<Inbox user={user} initialThreadId={4} />);
    await userEvent.click(await screen.findByRole("button", { name: "Suggest reply" }));
    await screen.findByText("Saved copy");
    expect(context.mock.calls.some(([references]) => references.currentDraftId === "active-draft" && references.workspacePath === "/inbox?thread=4&review=saved-review")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(recordWorkspaceContext).toHaveBeenLastCalledWith({ currentDraftId: "active-draft", workspacePath: "/inbox?thread=4&review=saved-review" }, user.id);
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Back to conversation" }));
    expect(recordWorkspaceContext).toHaveBeenLastCalledWith({ currentDraftId: null, workspacePath: "/inbox?thread=4" }, user.id);
  });
  test("returning from Chat restores the existing reply without generating another", async () => {
    const conversation = { id: 4, name: "Bruce", address: lead.email, can_reply: true, reply_blocker: "", total_messages: 0, messages: [] };
    call.mockImplementation(async path => path.startsWith("outreach/reviews/") ? { ...review, kind: "reply", thread_id: 4 } : path === "inbox/conversations/4" ? conversation : { items: [], total: 0, limit: 50, offset: 0 });
    render(<Inbox user={user} initialThreadId={4} initialReviewId={review.id} />);
    await screen.findByText("Saved copy");
    expect(screen.queryByRole("button", { name: "Suggest reply" })).toBeNull();
    expect(call.mock.calls.every(([, init]) => !init?.method)).toBe(true);
    expect(context.mock.calls.some(([references]) => references.currentDraftId === "active-draft" && references.workspacePath === "/inbox?thread=4&review=saved-review")).toBe(true);
  });
  test("a saved reply cannot be displayed under a different Inbox conversation", async () => {
    const conversation = { id: 4, name: "Bruce", address: lead.email, can_reply: true, reply_blocker: "", total_messages: 0, messages: [] };
    call.mockImplementation(async path => path.startsWith("outreach/reviews/") ? { ...review, kind: "reply", thread_id: 8 } : path === "inbox/conversations/4" ? conversation : { items: [], total: 0, limit: 50, offset: 0 });
    render(<Inbox user={user} initialThreadId={4} initialReviewId={review.id} />);
    await screen.findByText("This saved reply belongs to a different conversation.");
    expect(screen.queryByText("Saved copy")).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(call.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });
});
