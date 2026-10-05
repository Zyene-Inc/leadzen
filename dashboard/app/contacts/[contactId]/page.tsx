import { notFound } from "next/navigation";
import { requireAccount } from "@/lib/auth";
import LeadDetail from "@/components/lead-detail";

export default async function Page({ params }: { params: Promise<{ contactId: string }> }) {
  const user = await requireAccount({ onboarded: true });
  const { contactId } = await params;
  if (!/^\d{1,12}$/.test(contactId) || !Number.isSafeInteger(Number(contactId)) || Number(contactId) < 1) notFound();
  return <LeadDetail key={contactId} user={user} contactId={Number(contactId)} />;
}
