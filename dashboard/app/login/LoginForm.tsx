"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand } from "@/components/brand";
import { SecretInput } from "@/components/secret-input";
import { safeMcpReturnPath } from "@/lib/mcp-return";

export default function LoginForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as {
          error?: string;
        };
        setError(payload.error ?? "Unable to sign in");
        return;
      }
      const payload = (await response.json()) as {
        next: string;
        user: {
          must_change_password: boolean;
          onboarded: boolean;
          tour_completed: boolean;
          tour_started?: boolean;
          tour_skipped?: boolean;
          is_admin: boolean;
        };
      };
      const returnTo = safeMcpReturnPath(
        new URLSearchParams(window.location.search).get("returnTo"),
      );
      const canConnect =
        !payload.user.must_change_password &&
        payload.user.onboarded &&
        (payload.user.tour_completed ||
          payload.user.tour_started ||
          payload.user.tour_skipped ||
          payload.user.is_admin);
      router.replace(canConnect && returnTo ? returnTo : payload.next);
      router.refresh();
    } catch {
      setError(
        "Sign-in is unavailable. Please try again or contact support@zyene.com.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <Brand />
        <h1 id="login-title">Sign in to LeadZen</h1>
        <p>Zyene's private outreach workspace for its products and services.</p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <form className="login-form" onSubmit={submit}>
          <label htmlFor="email">Work email</label>
          <input
            className="input"
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <SecretInput
            label="Password"
            className="input"
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="login-support">
          Accounts are created by your administrator.
          <br />
          <a href="mailto:support@zyene.com">
            Need access? Contact support@zyene.com
          </a>
        </p>
      </section>
    </main>
  );
}
