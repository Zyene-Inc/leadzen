import { requireAccount } from "@/lib/auth";
import Admin from "@/components/admin";

export default async function AdminPage() {
  const user = await requireAccount({ admin: true });
  return <Admin user={user} />;
}
