"use client";

import { useEffect, useState } from "react";
import type { Conversation } from "@/lib/chat";

const eventName = "leadzen:workspace-updated";
const channelName = "leadzen-workspace-updates";
// A routing identifier, not an authentication token or Workspace identifier.
const senderId = Math.random().toString(36).slice(2);

export function notifyWorkspaceUpdated() {
  window.dispatchEvent(new Event(eventName));
  // Send an invalidation only. Each tab reads canonical data with its own session.
  try {
    const channel = new BroadcastChannel(channelName);
    channel.postMessage({ type: "refresh", sender: senderId });
    channel.close();
  } catch { /* Focus refresh remains available in older browsers. */ }
}

export function conversationWorkspaceVersion(value: Conversation) {
  return JSON.stringify([
    value.messages.filter((m) => m.role === "tool").map((m) => [m.id, m.data.result]),
    value.discovery && [value.discovery.id, value.discovery.counts, value.discovery.events.at(-1)?.id],
    value.run?.status,
  ]);
}

export function useWorkspaceRevision() {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision((value) => value + 1);
    const visible = () => { if (!document.hidden) refresh(); };
    let channel: BroadcastChannel | undefined;
    try {
      channel = new BroadcastChannel(channelName);
      channel.onmessage = (event) => {
        if (event.data?.type === "refresh" && event.data.sender !== senderId) refresh();
      };
    } catch { /* Local events and focus refresh still work. */ }
    window.addEventListener(eventName, refresh);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", visible);
    return () => { channel?.close(); window.removeEventListener(eventName, refresh); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", visible); };
  }, []);
  return revision;
}
