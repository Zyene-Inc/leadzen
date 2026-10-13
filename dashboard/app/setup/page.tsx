"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Brand } from "@/components/brand";
import { SecretInput } from "@/components/secret-input";
export default function SetupPage() {
  const token = useRef("");
  const [person, setPerson] = useState<{ name: string; email: string } | null>(
    null,
  );
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const secret =
      new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
    window.history.replaceState(null, "", "/setup");
    token.current = secret;
    if (!secret) {
      setError(
        "Open the setup link from your invite email. If it expired, ask your admin for a new one.",
      );
      return;
    }
    async function verify() {
      try {
        const response = await fetch("/api/auth/setup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: secret }),
        });
        const value = await response.json();
        if (!response.ok) throw new Error(value.error);
        setPerson(value);
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Could not check the setup link",
        );
      }
    }
    void verify();
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token.current, password }),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error);
      setDone(true);
      setPassword("");
      setConfirm("");
      token.current = "";
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not create password",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-card">
        <Brand />
        <h1>{done ? "You’re all set" : "Create your password"}</h1>
        <p>
          {person
            ? `Welcome, ${person.name}. Your account is ${person.email}.`
            : "Use your invite link to start."}
        </p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {done ? (
          <Link className="button primary" href="/login">
            Sign in
          </Link>
        ) : (
          person && (
            <form className="login-form" onSubmit={submit}>
              <SecretInput
                label="Password (12+ characters)"
                id="new-password"
                className="input"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <SecretInput
                label="Confirm password"
                id="confirm-password"
                className="input"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              <button type="submit" className="button primary" disabled={busy}>
                {busy ? "Creating…" : "Create password"}
              </button>
            </form>
          )
        )}
        <p className="login-support">
          <a href="mailto:support@zyene.com">support@zyene.com</a>
        </p>
      </section>
    </main>
  );
}
