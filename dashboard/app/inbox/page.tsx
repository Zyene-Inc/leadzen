import Inbox from "@/components/inbox";
import { requireAccount } from "@/lib/auth";

export default async function Page({ searchParams }: { searchParams: Promise<{ thread?: string; review?: string }> }) {
  const { thread, review } = await searchParams;
  const threadId = thread && /^\d{1,12}$/.test(thread) ? Number(thread) : null;
  return <Inbox initialThreadId={threadId} initialReviewId={threadId && review && /^[0-9a-f-]{36}$/.test(review) ? review : null} user={await requireAccount({ onboarded: true })} />;
}
