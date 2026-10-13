import ResultsPage from "@/components/results";
import { requireAccount } from "@/lib/auth";

export default async function Page() {
  return <ResultsPage user={await requireAccount({ onboarded: true })} />;
}
