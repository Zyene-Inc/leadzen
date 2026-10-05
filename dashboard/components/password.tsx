"use client";

import { useState, type FormEvent } from "react";
import { Brand } from "@/components/brand";
import { SecretInput } from "@/components/secret-input";
import type { Account } from "@/lib/auth";

export default function Password({ user }: { user: Account }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    if (data.get("new_password") !== data.get("confirm")) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: data.get("current_password"),
          new_password: data.get("new_password"),
        }),
      });
      const result = await response.json();
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok)
        throw new Error(result.error || "Could not change password");
      window.location.assign("/login?passwordChanged=1");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not change password",
      );
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-card">
        <Brand />
        <h1 className="auth-heading">Set your password</h1>
        <p>
          Set a private password for {user.email}. You’ll sign in again to
          continue to setup.
        </p>
        <form className="login-form" onSubmit={submit}>
          <SecretInput
            label="Current / temporary password"
            id="current"
            className="input"
            name="current_password"
            autoComplete="current-password"
            required
            maxLength={256}
          />
          <SecretInput
            label="New password"
            id="new"
            className="input"
            name="new_password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
          />
          <SecretInput
            label="Confirm new password"
            id="confirm"
            className="input"
            name="confirm"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
          />
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save password & sign in again"}
          </button>
        </form>
        <p>
          Use 12+ characters.{" "}
          <a className="support-link" href="mailto:support@zyene.com">
            Contact Zyene support
          </a>
        </p>
      </section>
    </main>
  );
}
