import { requireAccount } from "@/lib/auth";
import Tour from "@/components/tour";
export default async function Page() { return <Tour user={await requireAccount({ onboarded: true, skipTour: true })} />; }
