import { Activity } from "@/components/activity-feed";
import { requireAccount } from "@/lib/auth";

export default async function Page() {
  return <Activity user={await requireAccount({ onboarded: true })} />;
}
