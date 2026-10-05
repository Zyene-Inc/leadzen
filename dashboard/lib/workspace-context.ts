"use client";
import { useEffect } from "react";
import { api } from "@/lib/client-api";

export type WorkspaceReferences = {
  selectedLeadIds?: number[];
  currentLeadId?: number | null;
  currentDraftId?: string | null;
  currentThreadId?: number | null;
  currentRunId?: string | null;
  currentCampaignId?: string | null;
  workspacePath?: string;
  lastChatId?: string | null;
};
export type WorkspaceContext = WorkspaceReferences & {
  workspaceId: string; workspaceName: string; product: string;
  target: { summary: string };
  referencedLeads: { id: number; name: string }[];
};
let pending: Promise<unknown> = Promise.resolve();
let failure: unknown;
export function recordWorkspaceContext(references: WorkspaceReferences, actorId?: number) {
  // Serialize selection changes so a slower old request cannot overwrite the latest.
  pending = pending.catch(() => undefined).then(async () => {
    try {
      await api("chat/context", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(actorId ? { references, expected_actor_id: actorId } : references) });
      failure = undefined;
    } catch (error) { failure = error; }
  });
  return pending;
}
export async function flushWorkspaceContext() {
  await pending;
  if (failure) throw failure;
}
export function useWorkspaceContext(references: WorkspaceReferences, actorId?: number) {
  const encoded = JSON.stringify(references);
  useEffect(() => {
    const parsed = JSON.parse(encoded);
    if (Object.keys(parsed).length) void recordWorkspaceContext(parsed, actorId);
  }, [encoded, actorId]);
}
