import DiscoveryLive from "@/components/discovery-live";
import { requireAccount } from "@/lib/auth";
import { notFound } from "next/navigation";

export default async function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const user = await requireAccount({ onboarded: true });
  const { runId } = await params;
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      runId,
    )
  )
    notFound();
  return <DiscoveryLive key={runId} user={user} runId={runId} />;
}
