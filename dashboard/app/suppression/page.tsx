import { Suppression } from "@/components/workspace-records";
import { requireAccount } from "@/lib/auth";

export default async function Page() {
  return <Suppression user={await requireAccount({ onboarded: true })} />;
}
