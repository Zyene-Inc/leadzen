import { requireAccount } from "@/lib/auth";
import Contacts from "@/components/contacts";
export default async function Page() { return <Contacts user={await requireAccount({ onboarded: true })} />; }
