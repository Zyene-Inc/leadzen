import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Chat from "@/components/chat";
import { ToolResult } from "@/components/chat-results";
import { api } from "@/lib/client-api";
import { streamConversation } from "@/lib/chat-stream";
import type { Conversation, ChatMessage } from "@/lib/chat";
import { user, settings } from "./fixtures";
import { progress } from "./fixtures";

vi.mock("@/lib/chat-stream", () => ({ streamConversation: vi.fn() }));
const call = vi.mocked(api);
const live = vi.mocked(streamConversation);
const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const message = (overrides: Partial<ChatMessage> = {}): ChatMessage => ({ id: "assistant-1", role: "assistant", content: "Finding practice owners", data: { streaming: true }, created_at: "2026-10-03T12:00:00Z", ...overrides });
const conversation: Conversation = { id, title: "Practice owners", updated_at: "2026-10-03T12:00:00Z", messages: [message({ id: "user-1", role: "user", content: "Find five owners without emails", data: {} }), message()], run: { id: "run-1", status: "running", steps: 1, cancel_requested: false, approval: null, approval_expires_at: null } };
let saved: Conversation;

beforeEach(() => {
  saved = structuredClone(conversation);
  call.mockImplementation(async (path) => {
    if (path === "settings") return { ...settings, llm: { ...settings.llm, enabled: true, api_key_configured: true, model: "Synthetic model" } };
    if (path === "chat/threads") return { items: [saved] };
    return saved;
  });
  live.mockImplementation(async (_id, _receive, signal) => {
    await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
  });
});
async function ready() {
  await screen.findByRole("heading", { name: "Practice owners" });
  await waitFor(() => expect(live).toHaveBeenCalled());
}
function snapshot(value: Conversation) { act(() => live.mock.calls.at(-1)![1](value)); }

describe("Chat interaction", () => {
  test("composer stays outside the transcript scroll area while real text streams", async () => {
    const { container } = render(<Chat user={user} threadId={id} />);
    await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    const composer = container.querySelector("form.chat-composer")!;
    expect(viewport.contains(composer)).toBe(false);
    expect(composer.parentElement?.className).toBe("chat-composer-dock");
    snapshot({ ...saved, messages: [...saved.messages.slice(0, 1), message({ content: "Finding practice owners in Massachusetts…" })] });
    expect(screen.getByText("Finding practice owners in Massachusetts…")).toBeTruthy();
    expect(container.querySelectorAll(".chat-message.assistant")).toHaveLength(1);
    expect(container.querySelector(".chat-message.assistant .chat-message-text")?.getAttribute("aria-busy")).toBe("true");
    snapshot({ ...saved, messages: [message({ content: "Five owners saved", data: { streaming: false } })], run: { ...saved.run!, status: "succeeded" } });
    expect(container.querySelector(".stream-cursor")).toBeNull();
    expect(screen.queryByText("Writing a response")).toBeNull();
  });
  test("reading earlier messages pauses following; Jump to latest respects reduced motion", async () => {
    render(<Chat user={user} threadId={id} />);
    await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    fireEvent.keyDown(viewport, { key: "Home" });
    viewport.scrollTop = 200;
    fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "Jump to latest ↓" })).toBeTruthy();
    snapshot({ ...saved, messages: [message({ content: "New text while you read" })] });
    expect(viewport.scrollTop).toBe(200);
    const scrollTo = vi.fn(); viewport.scrollTo = scrollTo;
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    await userEvent.click(screen.getByRole("button", { name: "Jump to latest ↓" }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 1800, behavior: "instant" });
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
    vi.unstubAllGlobals();
    snapshot({ ...saved, messages: [message({ content: "Follow the newest response" })] });
    expect(viewport.scrollTop).toBe(1800);
  });
  test("actual in-flight tool text replaces generic thinking; composing cannot submit another run", async () => {
    saved.messages.push(message({ id: "tool-1", role: "tool", content: "Checking your saved leads", data: { tool: "list_leads", result: { status: "running" } } }));
    render(<Chat user={user} threadId={id} />); await ready();
    expect(screen.getAllByText("Checking your saved leads")).toHaveLength(1);
    expect(screen.getByText("View activity")).toBeTruthy();
    const input = screen.getByRole("textbox", { name: "Message LeadZen" });
    await userEvent.type(input, "Only owners please{Enter}");
    expect((input as HTMLTextAreaElement).value).toBe("Only owners please");
    expect(call.mock.calls.some(([path]) => path.endsWith("/messages"))).toBe(false);
    expect(screen.getByRole("button", { name: "Stop task" })).toBeTruthy();
  });
  test("smooth Jump to latest keeps its control hidden through intermediate positions", async () => {
    render(<Chat user={user} threadId={id} />); await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    fireEvent.keyDown(viewport, { key: "Home" });
    viewport.scrollTop = 200; viewport.scrollTo = vi.fn(); fireEvent.scroll(viewport);
    await userEvent.click(screen.getByRole("button", { name: "Jump to latest ↓" }));
    viewport.scrollTop = 500; fireEvent.scroll(viewport);
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
    snapshot({ ...saved, messages: [message({ content: "More text while scrolling" })] });
    expect(viewport.scrollTop).toBe(500);
    fireEvent(viewport, new Event("scrollend", { bubbles: true }));
    expect(viewport.scrollTop).toBe(1800);
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
  });
  test.each(["wheel", "touch", "keyboard"])("%s navigation interrupts smooth jumping and resumes reading earlier messages", async (input) => {
    render(<Chat user={user} threadId={id} />); await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    fireEvent.keyDown(viewport, { key: "Home" });
    viewport.scrollTop = 200;
    const scrollTo = vi.fn(); viewport.scrollTo = scrollTo; fireEvent.scroll(viewport);
    await userEvent.click(screen.getByRole("button", { name: "Jump to latest ↓" }));
    viewport.scrollTop = 500; fireEvent.scroll(viewport);
    if (input === "wheel") fireEvent.wheel(viewport, { deltaY: -100 });
    if (input === "touch") fireEvent.touchStart(viewport);
    if (input === "keyboard") fireEvent.keyDown(viewport, { key: "PageUp" });
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 500, behavior: "instant" });
    expect(screen.getByRole("button", { name: "Jump to latest ↓" })).toBeTruthy();
    snapshot({ ...saved, messages: [message({ content: "New response while reading" })] });
    expect(viewport.scrollTop).toBe(500);
    fireEvent(viewport, new Event("scrollend", { bubbles: true }));
    expect(viewport.scrollTop).toBe(500);
  });
  test("stop waits for backend cancellation and keeps the next typed message", async () => {
    render(<Chat user={user} threadId={id} />); await ready();
    await userEvent.type(screen.getByRole("textbox", { name: "Message LeadZen" }), "Make it shorter");
    await userEvent.click(screen.getByRole("button", { name: "Stop task" }));
    await waitFor(() => expect(call.mock.calls.some(([path]) => path === "chat/runs/run-1/cancel")).toBe(true));
    expect(screen.queryByText("Task stopped. Completed results are saved in Workspace.")).toBeNull();
    expect((screen.getByRole("textbox", { name: "Message LeadZen" }) as HTMLTextAreaElement).value).toBe("Make it shorter");
    snapshot({ ...saved, run: { ...saved.run!, status: "cancelled" } });
    expect(screen.getByText("Task stopped. Completed results are saved in Workspace.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send message" })).toBeTruthy();
  });
  test("Shift Enter and input-method Enter do not submit; plain Enter submits once", async () => {
    saved.run = null; saved.messages = [];
    render(<Chat user={user} threadId={id} />);
    const input = await screen.findByRole("textbox", { name: "Message LeadZen" });
    await waitFor(() => expect((input as HTMLTextAreaElement).disabled).toBe(false));
    await userEvent.type(input, "First line{Shift>}{Enter}{/Shift}Second line");
    expect((input as HTMLTextAreaElement).value).toBe("First line\nSecond line");
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229, isComposing: true });
    expect(call.mock.calls.some(([path]) => path.endsWith("/messages"))).toBe(false);
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    await waitFor(() => expect(call.mock.calls.filter(([path]) => path.endsWith("/messages"))).toHaveLength(1));
    expect(JSON.parse(String(call.mock.calls.find(([path]) => path.endsWith("/messages"))![1]?.body)).content).toBe("First line\nSecond line");
    expect(call.mock.calls.some(([path]) => path.endsWith("/approval"))).toBe(false);
  });
  test("accepted message followed by a refresh failure is not restored for duplicate submission", async () => {
    saved.run = null; saved.messages = []; let accepted = false;
    call.mockImplementation(async (path) => {
      if (path === "settings") return { ...settings, llm: { ...settings.llm, enabled: true, api_key_configured: true, model: "Synthetic model" } };
      if (path === "chat/threads") return { items: [saved] };
      if (path.endsWith("/messages")) { accepted = true; return {}; }
      if (accepted) throw new Error("Network interrupted");
      return saved;
    });
    render(<Chat user={user} threadId={id} />);
    const input = await screen.findByRole("textbox", { name: "Message LeadZen" });
    await waitFor(() => expect((input as HTMLTextAreaElement).disabled).toBe(false));
    await userEvent.type(input, "Find five owners{Enter}"); await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain("Your message was received");
    expect((input as HTMLTextAreaElement).value).toBe("");
    expect(call.mock.calls.filter(([path]) => path.endsWith("/messages"))).toHaveLength(1);
  });
  test("stopped tool is not marked complete and technical Workspace URL stays a link", () => {
    render(<ToolResult message={message({ role: "tool", content: "Drafting stopped", data: { tool: "create_drafts", result: { status: "stopped", note: "Review before retrying", workspaceUrl: "/sending" } } })} />);
    expect(screen.getByText("Stopped")).toBeTruthy();
    expect(screen.getByText("Review before retrying")).toBeTruthy();
    expect(screen.queryByText("workspaceUrl")).toBeNull();
    expect(screen.getByRole("link", { name: "Open in workspace →" }).getAttribute("href")).toBe("/sending");
  });
  test("current discovery work names the real candidate being evaluated", async () => {
    saved.run!.discovery_id = progress.id;
    saved.discovery = { ...progress, current_activity: { kind: "evaluating", data: { id: 4, name: "Sarah Johnson" }, created_at: "2026-10-03T12:00:00Z" } };
    saved.messages.push(message({ id: "tool-1", role: "tool", content: "Finding five leads", data: { tool: "find_leads", result: { status: "running" } } }));
    render(<Chat user={user} threadId={id} />); await ready();
    expect(screen.getAllByText("Evaluating Sarah Johnson").length).toBeGreaterThan(0);
  });
  test("switching history hides stale records while loading and resets following for the new conversation", async () => {
    saved.run = null;
    saved.messages = [message({ content: "Old thread record", data: {} })];
    const { rerender } = render(<Chat user={user} threadId={id} />);
    await screen.findByText("Old thread record");
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    fireEvent.keyDown(viewport, { key: "Home" });
    viewport.scrollTop = 200; fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "Jump to latest ↓" })).toBeTruthy();
    const nextId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    let resolve!: (value: Conversation) => void;
    call.mockImplementation(async (path) => {
      if (path === "settings") return { ...settings, llm: { ...settings.llm, enabled: true, api_key_configured: true, model: "Synthetic model" } };
      if (path === "chat/threads") return { items: [saved] };
      if (path === `chat/threads/${nextId}`) return await new Promise<Conversation>((done) => { resolve = done; });
      return saved;
    });
    rerender(<Chat user={user} threadId={nextId} />);
    expect(screen.queryByText("Old thread record")).toBeNull();
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
    await act(async () => resolve({ ...saved, id: nextId, title: "New conversation", messages: [message({ content: "New thread record", data: {} })] }));
    await screen.findByText("New thread record");
    expect(screen.getByRole("region", { name: "Conversation scroll area" })).not.toBe(viewport);
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
  });
  test("queued to running keeps the same live connection until the task completes", async () => {
    saved.run!.status = "queued";
    render(<Chat user={user} threadId={id} />); await ready();
    const signal = live.mock.calls[0][2];
    snapshot({ ...saved, run: { ...saved.run!, status: "running" } });
    expect(live).toHaveBeenCalledOnce();
    expect(signal.aborted).toBe(false);
    snapshot({ ...saved, run: { ...saved.run!, status: "succeeded" } });
    expect(signal.aborted).toBe(true);
  });
  test("ordinary card-growth scroll events keep following without showing Jump to latest", async () => {
    render(<Chat user={user} threadId={id} />); await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    viewport.scrollTop = 200;
    fireEvent.scroll(viewport);
    expect(viewport.scrollTop).toBe(1800);
    expect(screen.queryByRole("button", { name: "Jump to latest ↓" })).toBeNull();
    Object.defineProperty(viewport, "scrollHeight", { configurable: true, value: 2200 });
    snapshot({ ...saved, messages: [message({ content: "Another candidate evaluated" })] });
    expect(viewport.scrollTop).toBe(2200);
  });
  test("dragging the transcript scrollbar pauses following just like keyboard scrolling", async () => {
    render(<Chat user={user} threadId={id} />); await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    fireEvent.pointerDown(viewport, { button: 0 });
    viewport.scrollTop = 350; fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "Jump to latest ↓" })).toBeTruthy();
    snapshot({ ...saved, messages: [message({ content: "Newest candidate while reading older history" })] });
    expect(viewport.scrollTop).toBe(350);
  });
  test("transcript resize follows growth only until a user intentionally reads history, and observer cleans up", async () => {
    const observers: { callback: ResizeObserverCallback; observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }[] = [];
    vi.stubGlobal("ResizeObserver", class {
      observe = vi.fn(); disconnect = vi.fn();
      constructor(callback: ResizeObserverCallback) { observers.push({ callback, observe: this.observe, disconnect: this.disconnect }); }
    });
    const { unmount } = render(<Chat user={user} threadId={id} />); await ready();
    const viewport = screen.getByRole("region", { name: "Conversation scroll area" });
    const observer = observers.at(-1)!;
    expect(observer.observe).toHaveBeenCalledWith(viewport);
    expect(observer.observe).toHaveBeenCalledWith(screen.getByLabelText("Conversation messages"));
    Object.defineProperties(viewport, { scrollHeight: { configurable: true, value: 1800 }, clientHeight: { configurable: true, value: 600 } });
    act(() => observer.callback([], {} as ResizeObserver));
    expect(viewport.scrollTop).toBe(1800);
    fireEvent.wheel(viewport, { deltaY: -500 }); viewport.scrollTop = 400; fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "Jump to latest ↓" })).toBeTruthy();
    Object.defineProperty(viewport, "scrollHeight", { configurable: true, value: 2200 });
    act(() => observer.callback([], {} as ResizeObserver));
    expect(viewport.scrollTop).toBe(400);
    unmount();
    expect(observer.disconnect).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
  test("a rejected live connection falls back to actual saved progress without a stale warning", async () => {
    live.mockRejectedValueOnce(new Error("Could not connect to live Chat. Refreshing saved progress."));
    render(<Chat user={user} threadId={id} />); await ready();
    await waitFor(() => expect(call.mock.calls.filter(([path]) => path === `chat/threads/${id}`)).toHaveLength(2));
    expect(screen.queryByText("Could not connect to live Chat. Refreshing saved progress.")).toBeNull();
    expect(screen.getByText("Finding practice owners")).toBeTruthy();
  });
  test("a fresh stream snapshot clears a connection failure once progress recovers", async () => {
    let rejectConnection!: (error: Error) => void;
    live.mockImplementationOnce(async () => await new Promise<void>((_resolve, reject) => { rejectConnection = reject; }));
    render(<Chat user={user} threadId={id} />); await ready();
    call.mockRejectedValue(new Error("Offline"));
    await act(async () => rejectConnection(new Error("Live connection unavailable")));
    await screen.findByText("Live connection unavailable");
    snapshot({ ...saved, messages: [message({ content: "Recovered response", data: {} })], run: { ...saved.run!, status: "succeeded" } });
    expect(screen.getByText("Recovered response")).toBeTruthy();
    expect(screen.queryByText("Live connection unavailable")).toBeNull();
  });
});
