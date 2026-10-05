import { requireAccount } from "@/lib/auth";
import Chat from "@/components/chat";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ intent?: string }>;
}) {
  const { intent } = await searchParams;
  const prompt =
    intent === "find-leads"
      ? "Check my setup and saved target, then help me find 5 more qualified leads. Show me the search and any enrichment credits for approval before starting. Do not send emails."
      : intent === "review-replies"
        ? "Show my stored human replies and suggest next steps. Tell me if I need to sync my inbox for fresh replies."
        : intent === "sync-replies"
          ? "Check my inbox connection, then show the mailbox sync action for approval. After syncing, summarize new human replies, bounces and opt-outs. Do not send emails."
          : "";
  return (
    <Chat
      key={intent || "home"}
      user={await requireAccount({ onboarded: true })}
      initialPrompt={prompt}
    />
  );
}
