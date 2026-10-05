import { cookies } from "next/headers";
import { backend, requireAccount } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";
import type { Wizard } from "@/lib/setup-wizard";
import Onboarding from "@/components/onboarding";

export default async function OnboardingPage() {
  const user = await requireAccount();
  let initial: Wizard | null = null;
  try {
    const response = await backend(
      "onboarding/wizard",
      {},
      (await cookies()).get(SESSION_COOKIE)?.value,
    );
    if (response.ok) initial = (await response.json()) as Wizard;
  } catch {
    /* The client displays a retry action without exposing server details. */
  }
  return <Onboarding user={user} initial={initial} />;
}
