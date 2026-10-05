import { requireAccount } from "@/lib/auth";
import Password from "@/components/password";

export default async function PasswordPage() {
  const user = await requireAccount({ allowPasswordChange: true });
  return <Password user={user} />;
}
