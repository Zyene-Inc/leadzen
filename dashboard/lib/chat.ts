import type { WorkspaceContext } from "@/lib/workspace-context";
import type { DiscoveryProgress } from "@/lib/discovery";
export function workspaceLink(value: unknown): string | null {
  return typeof value === "string" && /^(?:\/inbox\?thread=\d{1,12}&review=[0-9a-f-]{36}|\/(?:contacts(?:\/\d+)?|campaigns|outreach|sending|inbox|find-leads(?:\/[0-9a-f-]{36})?|settings|suppression|activity)(?:\?(?:review|thread|campaign)=[0-9a-f-]+)?)$/.test(value) ? value : null;
}
export type ChatThread = { id: string; title: string; updated_at: string };
export type Approval = {
  id: string;
  tool: string;
  summary: string;
  credits: number;
  emails: number;
  preview: Record<string, unknown>;
};
export type ChatRun = {
  id: string;
  status: string;
  steps: number;
  cancel_requested: boolean;
  created_at?: string;
  finished_at?: string | null;
  discovery_id?: string | null;
  approval: Approval | null;
  approval_expires_at: string | null;
};
export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  data: { tool?: string; result?: Record<string, unknown>; streaming?: boolean };
  created_at: string;
};
export type Conversation = ChatThread & {
  context?: WorkspaceContext;
  discovery?: DiscoveryProgress;
  messages: ChatMessage[];
  run: ChatRun | null;
};
/** Live snapshots carry progress at the top level; history keeps it in the tool result. */
export function currentRunDiscovery(conversation: Conversation) {
  const id = conversation.run?.discovery_id;
  if (!id) return undefined;
  if (conversation.discovery?.id === id) return conversation.discovery;
  for (const message of [...conversation.messages].reverse()) {
    const saved = message.data.result?.discovery as DiscoveryProgress | undefined;
    if (saved?.id === id) return saved;
  }
  return undefined;
}
export const activeRun = (run: ChatRun | null | undefined) =>
  !!run && ["queued", "running", "awaiting_approval", "paused"].includes(run.status);
