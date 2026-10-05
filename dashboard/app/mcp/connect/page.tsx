import { requireAccount } from "@/lib/auth";
import MCPConsent from "@/components/mcp-consent";

export default async function MCPConnectPage({ searchParams }: { searchParams: Promise<{ request?: string | string[] }> }) {
  const params = await searchParams;
  const request = typeof params.request === "string" ? params.request : "";
  const user = await requireAccount({ onboarded: true, skipTour: true, returnTo: `/mcp/connect?request=${encodeURIComponent(request)}` });
  return <MCPConsent user={user} request={request} />;
}
