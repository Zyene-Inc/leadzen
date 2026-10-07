import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatResponse } from "@/components/chat-response";
import { ChatHistory } from "@/components/chat-history";
import { notifyWorkspaceUpdated, useWorkspaceRevision, conversationWorkspaceVersion } from "@/lib/workspace-updates";
import { useStoredData } from "@/lib/use-stored-data";
import { api } from "@/lib/client-api";
import type { Conversation } from "@/lib/chat";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

test("assistant responses render formatted prose and safe tables without remote images or HTML", () => {
  const { container } = render(<ChatResponse content={'## Saved leads\n\n**Sarah** is qualified.\n\n- Practice owner\n- Massachusetts\n\n| Name | Status |\n| --- | --- |\n| Sarah | Qualified |\n\n`lead_1`\n\n[Workspace](/contacts/1)\n\n[Bad](javascript:alert%281%29)\n\n<img src="https://example.com/track" />\n\n![tracking](https://example.com/track)'} />);
  expect(screen.getByRole("heading", { name: "Saved leads" })).toBeTruthy();
  expect(container.querySelector("strong")?.textContent).toBe("Sarah");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Workspace" }).getAttribute("href")).toBe("/contacts/1");
  expect(container.querySelectorAll('img, script, a[href^="javascript:"]')).toHaveLength(0);
});

test("newly received text reveals progressively; final content and restored history are immediate", () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  let tick: FrameRequestCallback = () => {};
  vi.stubGlobal("requestAnimationFrame", vi.fn((fn) => { tick = fn; return 1; }));
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  const { rerender, container } = render(<ChatResponse content="Hello" streaming />);
  rerender(<ChatResponse content="Hello Sarah, your five leads are saved." streaming />);
  expect(container.textContent).not.toContain("five leads are saved");
  act(() => tick(0));
  expect(container.textContent).toContain("Hello S");
  // Mid-animation still hides the tail; the effect stretches ~600 ms so the
  // rendered text visibly advances frame by frame.
  act(() => tick(120));
  expect(container.textContent).not.toContain("five leads are saved.");
  act(() => tick(600));
  expect(container.textContent).toContain("Hello Sarah, your five leads are saved.");
  rerender(<ChatResponse content="A corrected final answer." />);
  expect(container.textContent).toBe("A corrected final answer.");
  expect(container.querySelector('.stream-cursor')).toBeNull();
});

test("reduced motion and replacement text skip the reveal queue", () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
  const { rerender, container } = render(<ChatResponse content="First" streaming />);
  rerender(<ChatResponse content="First second third" streaming />);
  expect(container.textContent).toContain("First second third");
  rerender(<ChatResponse content="Corrected" streaming />);
  expect(container.textContent).toContain("Corrected");
  expect(container.textContent).not.toContain("First");
});

const item = { id: "chat-1", title: "Dental owners", updated_at: "2026-10-03T12:00:00Z" };
test("sidebar deletion is explicit, cancellable, and waits for the canonical API result", async () => {
  let resolve: () => void = () => {};
  const remove = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
  render(<ChatHistory items={[item]} selected={item.id} onDelete={remove} />);
  await userEvent.click(screen.getByRole("button", { name: "Delete chat: Dental owners" }));
  expect(screen.getByRole("dialog").textContent).toContain("Leads, drafts, campaigns, and outreach records stay in Workspace");
  expect(remove).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Delete chat: Dental owners" }));
  await userEvent.click(screen.getByRole("button", { name: "Delete chat" }));
  expect(remove).toHaveBeenCalledExactlyOnceWith("chat-1");
  expect((screen.getByRole("button", { name: "Deleting…" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => resolve());
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("failed deletion keeps the chat and explains why it cannot be deleted", async () => {
  render(<ChatHistory items={[item]} onDelete={vi.fn().mockRejectedValue(new Error("Finish or stop the current task first"))} />);
  await userEvent.click(screen.getByRole("button", { name: "Delete chat: Dental owners" }));
  await userEvent.click(screen.getByRole("button", { name: "Delete chat" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Finish or stop the current task first");
  expect(screen.getByRole("link", { name: /Dental owners/ })).toBeTruthy();
});

test("a Chat save refreshes already mounted Workspace data without navigation or polling", async () => {
  const call = vi.mocked(api);
  call.mockResolvedValueOnce({ total: 0 }).mockResolvedValue({ total: 5 });
  function Workspace() { const { data } = useStoredData<{total:number}>("leads"); return <p>Saved leads: {data?.total ?? "loading"}</p>; }
  render(<Workspace />);
  await screen.findByText("Saved leads: 0");
  act(() => notifyWorkspaceUpdated());
  await screen.findByText("Saved leads: 5");
  expect(call).toHaveBeenCalledTimes(2);
});

test("cross-tab notifications contain no records and refresh listeners close on unmount", async () => {
  const channels: { onmessage?: (event: {data:unknown}) => void; close: ReturnType<typeof vi.fn>; postMessage: ReturnType<typeof vi.fn> }[] = [];
  vi.stubGlobal("BroadcastChannel", class { onmessage?: (event: {data:unknown}) => void; close = vi.fn(); postMessage = vi.fn(); constructor() { channels.push(this); } });
  function Workspace() { const version = useWorkspaceRevision(); return <p>Revision {version}</p>; }
  const { unmount } = render(<Workspace />);
  act(() => channels[0].onmessage?.({data:{type:"refresh",sender:"another-tab"}}));
  await screen.findByText("Revision 1");
  act(() => notifyWorkspaceUpdated());
  expect(channels[1].postMessage).toHaveBeenCalledExactlyOnceWith({type:"refresh",sender:expect.any(String)});
  act(() => channels[0].onmessage?.({data:channels[1].postMessage.mock.calls[0][0]}));
  expect(screen.getByText("Revision 2")).toBeTruthy();
  expect(channels[1].close).toHaveBeenCalled();
  unmount();
  expect(channels[0].close).toHaveBeenCalled();
});

test("streamed prose alone does not invalidate records; changed tool results do", () => {
  const saved = { messages: [{ id:"m1",role:"assistant",content:"Hello",data:{} }], run:{status:"running"} } as Conversation;
  expect(conversationWorkspaceVersion(saved)).toBe(conversationWorkspaceVersion({...saved,messages:[{...saved.messages[0],content:"Hello Sarah"}]}));
  expect(conversationWorkspaceVersion(saved)).not.toBe(conversationWorkspaceVersion({...saved,messages:[...saved.messages,{...saved.messages[0],id:"tool",role:"tool",data:{result:{status:"completed",leadId:1}}}]}));
});
