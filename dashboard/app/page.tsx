import { requireAccount } from "@/lib/auth";
import Overview from "@/components/overview";

export default async function Page() {
  return <Overview user={await requireAccount({ onboarded: true })} />;
}
