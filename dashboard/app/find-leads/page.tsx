import FindLeads from "@/components/find-leads";
import { requireAccount } from "@/lib/auth";

export default async function Page() {
  return <FindLeads user={await requireAccount({ onboarded: true })} />;
}
