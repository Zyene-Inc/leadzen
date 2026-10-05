import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import Chat from "@/components/chat";
import Campaigns from "@/components/campaigns";
import { ChatRename } from "@/components/chat-rename";
import { ApprovalCard, ToolResult } from "@/components/chat-results";
import { ChatDiscoveryCard } from "@/components/chat-discovery-card";
import { streamConversation } from "@/lib/chat-stream";
import { api } from "@/lib/client-api";
import type { Conversation, Approval, ChatMessage } from "@/lib/chat";
import { workspaceLink } from "@/lib/chat";
import { recordWorkspaceContext } from "@/lib/workspace-context";
import { user, settings, progress } from "./fixtures";
const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/" }));
const ActualSidebar = (await vi.importActual<typeof import("@/components/sidebar")>("@/components/sidebar")).Sidebar;

const call = vi.mocked(api);
const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const draftId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const context = { workspaceId: "w1", workspaceName: "Dental Workspace", product: "Reviews", target: { summary: "Practice owners" }, selectedLeadIds: [1, 2, 3], currentLeadId: 1, currentDraftId: draftId, referencedLeads: [{ id: 1, name: "Sarah Johnson" }] };
const conversation: Conversation = { id, title: "Dental owners", updated_at: "2026-10-02T12:00:00Z", context, messages: [], run: null };
const approval: Approval = { id: "server-issued", tool: "send_email", summary: "Send this reviewed message?", credits: 0, emails: 1, preview: { from_address: "sender@example.com", recipients: [{ id: draftId, name: "Sarah Johnson", email: "sarah@example.com", subject: "Quick question", body: "Complete exact message.\nSignature and opt-out." }] } };
const message = (tool: string, result: Record<string, unknown>): ChatMessage => ({ id: "m1", role: "tool", content: "Saved result", data: { tool, result }, created_at: "2026-10-02T12:00:00Z" });
beforeEach(() => { HTMLElement.prototype.scrollIntoView = vi.fn(); });

for (let repetition = 1; repetition <= 10; repetition++) describe(`Chat agent pass ${repetition}`, () => {
  test("confirmation displays complete copy, mailbox and exact recipients before send", async () => {
    const decide = vi.fn();
    render(<ApprovalCard approval={approval} expiresAt={null} busy={false} onApprove={decide} />);
    expect(screen.getByText("sender@example.com")).toBeTruthy();
    expect(screen.getByText("Quick question")).toBeTruthy();
    expect(screen.getByText(/Complete exact message/)).toBeTruthy();
    expect(decide).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm send" }));
    expect(decide.mock.calls).toEqual([[true]]);
  });
  test("paid lookup shows selected leads, credit cap and cancel", async () => {
    const decide = vi.fn();
    render(<ApprovalCard approval={{ ...approval, tool: "find_work_emails", credits: 3, emails: 0 }} expiresAt={null} busy={false} onApprove={decide} />);
    expect(screen.getByText("Selected leads: 1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Get emails" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(decide.mock.calls).toEqual([[false]]);
  });
  test("draft card is not sent and links to the canonical Workspace review", async () => {
    const command = vi.fn();
    render(<ToolResult message={message("create_drafts", { from_address: "sender@example.com", workspaceUrl: `/sending?review=${id}`, drafts: [{ id: draftId, name: "Sarah Johnson", to: "sarah@example.com", subject: "Quick question", body: "Draft copy", state: "pending" }] })} onCommand={command} />);
    expect(screen.getByText("Draft · not sent")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open in Workspace/ }).getAttribute("href")).toBe(`/sending?review=${id}`);
    await userEvent.click(screen.getByRole("button", { name: "Review sending" }));
    expect(command.mock.calls[0][0]).toContain(draftId);
    expect(call).not.toHaveBeenCalled();
  });
  test("lead qualification and reply cards link to actual records", async () => {
    const command = vi.fn();
    const { rerender } = render(<ToolResult message={message("list_leads", { items: [{ id: 17, name: "Sarah Johnson", title: "Owner", company: "Bright Smile", reason: "Owns a dental practice", state: "Ready" }] })} />);
    expect(screen.getByText("Owns a dental practice")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sarah Johnson" }).getAttribute("href")).toBe("/contacts/17");
    rerender(<ToolResult message={message("list_replies", { items: [{ id: 2, threadId: 9, from: "sarah@example.com", subject: "Pricing", body: "Can you send pricing?", workspaceUrl: "/inbox?thread=9" }] })} onCommand={command} />);
    await userEvent.click(screen.getByRole("button", { name: "Draft reply" }));
    expect(command.mock.calls[0][0]).toContain("conversation 9");
  });
  test("discovery shows persisted counts and actual reasons without default raw logs", () => {
    render(<ChatDiscoveryCard data={{ ...progress, leads: [{ id: 1, source_id: 8, contact_id: 17, name: "Sarah Johnson", company: "Bright Smile", title: "Owner", reason: "Owns a dental practice", email: "", profile_url: "", outcome: "qualified" }] }} />);
    expect(screen.getByRole("progressbar", { name: "Discovery goal" })).toBeTruthy();
    expect(screen.getByText("Email credits used")).toBeTruthy();
    expect(screen.getByText("Owns a dental practice")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open in Workspace/ }).getAttribute("href")).toBe("/contacts/17");
    expect(screen.queryByText("[DEBUG]")).toBeNull();
  });
  test("context is visible and rename persists without creating a new conversation", async () => {
    call.mockImplementation(async (path, init) => {
      if (path === "settings") return { ...settings, llm: { ...settings.llm, enabled: true, api_key_configured: true, model: "synthetic" } };
      if (path === "chat/threads") return { items: [conversation] };
      if (init?.method === "PUT") return { ...conversation, title: "Follow up with Sarah" };
      return conversation;
    });
    render(<Chat user={user} threadId={id} />);
    await screen.findByText(/3 selected leads/);
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const input = screen.getByRole("textbox", { name: "Conversation name" });
    await userEvent.clear(input); await userEvent.type(input, "Follow up with Sarah");
    await userEvent.click(screen.getByRole("button", { name: "Save name" }));
    await waitFor(() => expect(call.mock.calls.some(([path, init]) => path === `chat/threads/${id}` && init?.method === "PUT")).toBe(true));
    expect(call.mock.calls.some(([path, init]) => path === "chat/threads" && init?.method === "POST")).toBe(false);
  });
  test("duplicate message submits have one stable request and no implicit approval", async () => {
    let resolve!: () => void;
    call.mockImplementation(async (path, init) => {
      if (path === "settings") return { ...settings, llm: { ...settings.llm, enabled: true, api_key_configured: true, model: "synthetic" } };
      if (path === "chat/threads") return { items: [conversation] };
      if (path.endsWith("/messages")) await new Promise<void>((done) => { resolve = done; });
      return conversation;
    });
    const { container } = render(<Chat user={user} threadId={id} />);
    await waitFor(() => expect((screen.getByRole("textbox", { name: "Message LeadZen" }) as HTMLTextAreaElement).disabled).toBe(false));
    await userEvent.type(screen.getByRole("textbox", { name: "Message LeadZen" }), "Looks good.");
    const form = container.querySelector("form.chat-composer")!;
    fireEvent.submit(form); fireEvent.submit(form);
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    const writes = call.mock.calls.filter(([path]) => path.endsWith("/messages"));
    expect(writes).toHaveLength(1);
    expect(JSON.parse(String(writes[0][1]?.body)).content).toBe("Looks good.");
    expect(call.mock.calls.some(([path]) => path.endsWith("/approval"))).toBe(false);
    resolve();
  });
  test("real SSE snapshots survive split UTF-8 chunks and preserve object references", async () => {
    const bytes = new TextEncoder().encode(`data: ${JSON.stringify({ ...conversation, title: "Sarah’s conversation" })}\n\n: heartbeat\n\ndata: ${JSON.stringify({ ...conversation, title: "Finished" })}\n\n`);
    const body = new ReadableStream<Uint8Array>({ start(controller) { for (let index = 0; index < bytes.length; index += 7) controller.enqueue(bytes.slice(index, index + 7)); controller.close(); } });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200 })));
    const receive = vi.fn();
    await streamConversation(id, receive, new AbortController().signal);
    expect(receive).toHaveBeenCalledTimes(2);
    expect(receive.mock.calls[0][0].title).toBe("Sarah’s conversation");
    expect(receive.mock.calls[1][0].context.currentDraftId).toBe(draftId);
    vi.unstubAllGlobals();
  });
  test("external or protocol-relative links never enter Workspace navigation", () => {
    expect(workspaceLink("https://evil.example")).toBeNull();
    expect(workspaceLink("//evil.example")).toBeNull();
    expect(workspaceLink("javascript:alert(1)")).toBeNull();
    expect(workspaceLink(`/sending?review=${id}`)).toBe(`/sending?review=${id}`);
    expect(workspaceLink(`/inbox?thread=4&review=${id}`)).toBe(`/inbox?thread=4&review=${id}`);
    expect(workspaceLink(`/inbox?thread=4&review=${id}&other=1`)).toBeNull();
    expect(workspaceLink(`/inbox?thread=4&review=${id}#fragment`)).toBeNull();
  });
  test("email lookup renders actual status and unknown credit usage", () => {
    render(<ToolResult message={message("find_work_emails", { items: [{ id: 17, name: "Sarah Johnson", email: "", workspaceUrl: "/contacts/17" }], credits: { used: null } })} />);
    expect(screen.getByText("No verified email found")).toBeTruthy();
    expect(screen.getByText("Credits actually used: Awaiting provider report")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Open in Workspace/ })[0].getAttribute("href")).toBe("/contacts/17");
  });
  test("rename failure keeps the entered title available for correction", async () => {
    const save = vi.fn(async () => false), close = vi.fn();
    function Rename() { const [title, change] = useState("Old title"); return <ChatRename title={title} change={change} busy={false} save={save} close={close} />; }
    render(<Rename />);
    const input = screen.getByRole("textbox", { name: "Conversation name" });
    await userEvent.clear(input); await userEvent.type(input, "Massachusetts Dental Owners");
    await userEvent.click(screen.getByRole("button", { name: "Save name" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith("Massachusetts Dental Owners"));
    expect(close).not.toHaveBeenCalled();
    expect((input as HTMLInputElement).value).toBe("Massachusetts Dental Owners");
  });
  test("returning to the campaign picker restores the same canonical lead selection", async () => {
    call.mockImplementation(async (path) => path === "campaigns" ? { items: [] } : { items: [{ id: 17, name: "Sarah Johnson", email: "sarah@example.com", company: "Bright Smile" }] });
    render(<Campaigns user={user} initialSelection={[17]} />);
    const checkbox = await screen.findByRole("checkbox", { name: /Sarah Johnson/ });
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(call.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });
  test("switching from Dashboard retains the current page and existing chat", async () => {
    call.mockResolvedValue({ ...context, workspacePath: "/contacts/17", lastChatId: id });
    render(<ActualSidebar user={user} active="overview" />);
    await userEvent.click(screen.getByRole("link", { name: "Chat" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith(`/chat/${id}`));
    expect(recordWorkspaceContext).toHaveBeenCalledWith({ workspacePath: "/" }, user.id);
  });
  test("Workspace mode returns to the active canonical draft review", async () => {
    call.mockResolvedValue({ ...context, workspacePath: `/sending?review=${id}`, lastChatId: id });
    render(<ActualSidebar user={user} active="chat" />);
    await waitFor(() => expect(screen.getByRole("link", { name: "Workspace" }).getAttribute("href")).toBe(`/sending?review=${id}`));
    expect(call.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });
});
