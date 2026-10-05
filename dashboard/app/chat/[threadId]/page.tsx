import { requireAccount } from "@/lib/auth";
import Chat from "@/components/chat";
import { notFound } from "next/navigation";

export default async function Page({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = await params;
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      threadId,
    )
  )
    notFound();
  return (
    <Chat
      key={threadId}
      user={await requireAccount({ onboarded: true })}
      threadId={threadId}
    />
  );
}
