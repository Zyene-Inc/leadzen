import { cookies } from "next/headers";
import { backend, requireAccount } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";
import Outreach from "@/components/campaigns";
export default async function Page({ searchParams }: { searchParams: Promise<{ review?: string; campaign?: string; lead?: string }> }) {
  const user = await requireAccount({ onboarded: true });
  const params = await searchParams;
  const uuid = (value?: string) => value && /^[0-9a-f-]{36}$/.test(value) ? value : null;
  let selected: number[] = [];
  try {
    const response = await backend("chat/context", {}, (await cookies()).get(SESSION_COOKIE)?.value);
    if (response.ok) {
      const context = await response.json();
      if (["/outreach", "/campaigns"].includes(context.workspacePath)) selected = context.selectedLeadIds || [];
    }
  } catch { /* Selection is optional; ownership is checked by the API. */ }
  if (params.lead && /^\d{1,12}$/.test(params.lead)) selected = [Number(params.lead)];
  return <Outreach user={user} initialSelection={selected} initialReviewId={uuid(params.review)} initialCampaignId={uuid(params.campaign)} />;
}
