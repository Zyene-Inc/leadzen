import type { Conversation } from "@/lib/chat";

export async function streamConversation(id: string, receive: (value: Conversation) => void, signal: AbortSignal) {
  const response = await fetch(`/api/proxy/chat/threads/${id}/stream`, { signal, cache: "no-store" });
  if (!response.ok || !response.body) throw new Error("Could not connect to live Chat. Refreshing saved progress.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let frame: string[] = [];
  let frameSize = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener("abort", cancel, { once: true });
  function acceptLine(line: string) {
    if (line) {
      frameSize += line.length;
      if (frameSize > 8000000) throw new Error("Live update exceeded its size limit");
      frame.push(line);
      return;
    }
    let event = "message";
    const data: string[] = [];
    for (const entry of frame) {
      if (entry.startsWith(":")) continue;
      const separator = entry.indexOf(":");
      const field = separator < 0 ? entry : entry.slice(0, separator);
      const raw = separator < 0 ? "" : entry.slice(separator + 1);
      const value = raw.startsWith(" ") ? raw.slice(1) : raw;
      if (field === "event") event = value;
      if (field === "data") data.push(value);
    }
    frame = [];
    frameSize = 0;
    if (event === "expired") throw new Error("Your session expired. Sign in again.");
    if (data.length) receive(JSON.parse(data.join("\n")) as Conversation);
  }
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (signal.aborted) break;
      pending += done ? decoder.decode() : decoder.decode(value, { stream: true });
      if (pending.length + frameSize > 8000000) throw new Error("Live update exceeded its size limit");
      let end: number;
      while ((end = pending.indexOf("\n")) >= 0) {
        const line = pending.slice(0, end).replace(/\r$/, "");
        pending = pending.slice(end + 1);
        acceptLine(line);
      }
      if (done) break;
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
