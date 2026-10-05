"use client";
import { PageHeading } from "@/components/page-heading";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { SetupAudience } from "@/components/setup-audience";
import { api } from "@/lib/client-api";
import {
  initialDraft,
  stepValues,
  type Audience,
  type Country,
} from "@/lib/setup-wizard";
import type { Account } from "@/lib/auth";

type Target = {
  audience: Audience | null;
  summary: string;
  countries: Country[];
  accepted_legal_notice: boolean;
};

function TargetForm({ target }: { target: Target }) {
  const router = useRouter();
  const [draft, setDraft] = useState(() =>
    initialDraft({
      draft: {
        ...(target.audience ? { audience: target.audience } : {}),
        legacy_target: target.audience ? "" : target.summary,
        accepted_legal_notice: target.accepted_legal_notice,
        confirmed: false,
      },
    }),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api("target", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(stepValues(6, draft)),
      });
      router.push("/");
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save target",
      );
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="settings-form">
      <fieldset className="home-target-fieldset" disabled={busy}>
        <legend className="sr-only">Edit target audience</legend>
        <SetupAudience
          draft={draft}
          countries={target.countries}
          onChange={setDraft}
        />
      </fieldset>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="home-target-actions">
        <Link className="button" href="/">
          Cancel
        </Link>
        <button className="button primary" disabled={busy} type="submit">
          {busy ? "Saving…" : "Save target"}
        </button>
      </div>
    </form>
  );
}

export default function TargetEditor({ user }: { user: Account }) {
  const [target, setTarget] = useState<Target | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void api<Target>("target", { signal: controller.signal })
      .then(setTarget)
      .catch((caught) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught.message : "Could not load target",
          );
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <div className="shell">
      <Sidebar user={user} active="overview" />
      <main className="main">
        <div className="topbar">
          <PageHeading title="Edit your target" help="Update the audience used for new discovery requests. Existing contacts and past qualification decisions stay unchanged." />
        </div>
        {error ? (
          <div className="error" role="alert">
            {error}
            <button
              type="button"
              className="button"
              onClick={() => {
                setError("");
                setAttempt((value) => value + 1);
              }}
            >
              Try again
            </button>
          </div>
        ) : target ? (
          <TargetForm target={target} />
        ) : (
          <p role="status">Loading your target…</p>
        )}
      </main>
    </div>
  );
}
