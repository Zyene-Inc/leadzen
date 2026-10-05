"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { flushWorkspaceContext, recordWorkspaceContext, type WorkspaceReferences } from "@/lib/workspace-context";
import { Icon } from "@/components/icon";

export function AskLeadZen({ actorId, context, beforeOpen }: { actorId: number; context: WorkspaceReferences; beforeOpen?: () => Promise<WorkspaceReferences> }) {
  const router = useRouter();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function open() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const saved = beforeOpen ? await beforeOpen() : {};
      await recordWorkspaceContext({ selectedLeadIds: [], currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null, ...context, ...saved }, actorId);
      await flushWorkspaceContext();
      router.push("/chat");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not open your assistant"); }
    finally { pending.current = false; setBusy(false); }
  }
  return <span className="context-assistant"><button type="button" className="button ghost" disabled={busy} onClick={() => void open()}><Icon name="chat" />{busy ? "Opening…" : "Ask LeadZen"}</button>{error && <span className="error" role="alert">{error}</span>}</span>;
}
