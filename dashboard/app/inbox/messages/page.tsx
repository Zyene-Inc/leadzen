import { Inbox } from "@/components/workspace-records";
import { requireAccount } from "@/lib/auth";

export default async function Page() {
  return <Inbox user={await requireAccount({ onboarded: true })} />;
}
