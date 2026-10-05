import { requireAccount } from "@/lib/auth";
import Settings from "@/components/settings";

export default async function Page() {
  return <Settings user={await requireAccount({ onboarded: true })} />;
}
