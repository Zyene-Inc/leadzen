import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backend } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";
import LoginForm from "@/app/login/LoginForm";

export default async function LoginPage() {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (token) {
    let ok = false;
    try {
      ok = (await backend("auth/me", {}, token)).ok;
    } catch {
      // Connection hiccup: fall through to the form instead of trapping the user.
    }
    if (ok) redirect("/");
  }
  return <LoginForm />;
}
