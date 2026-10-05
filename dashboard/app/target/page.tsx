import { requireAccount } from "@/lib/auth";
import TargetEditor from "@/components/target-editor";

export default async function Page() {
  return <TargetEditor user={await requireAccount({ onboarded: true })} />;
}
