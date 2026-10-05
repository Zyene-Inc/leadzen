import { afterEach, describe, expect, test, vi } from "vitest";
import { streamConversation } from "@/lib/chat-stream";
import type { Conversation } from "@/lib/chat";

const saved: Conversation = { id: "canonical-thread", title: "Sarah’s clinic 🦷", updated_at: "2026-10-03T12:00:00Z", messages: [], run: null };
function serve(text: string, chunk = 1) {
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream<Uint8Array>({ start(controller) { for (let i = 0; i < bytes.length; i += chunk) controller.enqueue(bytes.slice(i, i + chunk)); controller.close(); } });
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body)));
}
afterEach(() => vi.unstubAllGlobals());

describe("Chat SSE protocol", () => {
  test("CRLF boundaries, comments and data without spaces survive bytewise UTF-8 delivery", async () => {
    serve(`: heartbeat\r\n\r\nevent: message\r\ndata:${JSON.stringify(saved)}\r\n\r\n`);
    const receive = vi.fn();
    await streamConversation(saved.id, receive, new AbortController().signal);
    expect(receive.mock.calls).toEqual([[saved]]);
  });
  test("multiline standard SSE data is joined before parsing", async () => {
    const json = JSON.stringify(saved, null, 2).split("\n").map((line) => `data: ${line}`).join("\n");
    serve(`${json}\n\n`, 17);
    const receive = vi.fn();
    await streamConversation(saved.id, receive, new AbortController().signal);
    expect(receive).toHaveBeenCalledWith(saved);
  });
  test("session expiration is detected regardless of field order", async () => {
    serve("data: {}\nevent: expired\n\n", 4);
    const receive = vi.fn();
    await expect(streamConversation(saved.id, receive, new AbortController().signal)).rejects.toThrow("Your session expired");
    expect(receive).not.toHaveBeenCalled();
  });
  test("aborting a quiet stream cancels its pending reader without a later UI update", async () => {
    const cancelled = vi.fn();
    const body = new ReadableStream<Uint8Array>({ cancel: cancelled });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body)));
    const controller = new AbortController();
    const receive = vi.fn();
    const completion = streamConversation(saved.id, receive, controller.signal);
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    controller.abort();
    await completion;
    expect(cancelled).toHaveBeenCalledOnce();
    expect(receive).not.toHaveBeenCalled();
  });
  test("malformed snapshot fails safely instead of presenting an invented result", async () => {
    serve("data: invalid-json\n\n");
    const receive = vi.fn();
    await expect(streamConversation(saved.id, receive, new AbortController().signal)).rejects.toThrow();
    expect(receive).not.toHaveBeenCalled();
  });
});
