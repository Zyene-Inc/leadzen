"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client-api";
import type { EmailReview } from "@/lib/discovery";

export default function DiscoveryEmailReview({
  runId,
  close,
}: {
  runId: string;
  close: () => void;
}) {
  const router = useRouter();
  const [review, setReview] = useState<EmailReview | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const request = useRef<{ selection: string; id: string } | null>(null);
  const submitting = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const selectedIds = new Set(selected);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setReview(null);
    setSelected([]);
    setError("");
    void api<EmailReview>(`discovery/${runId}/emails`, {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setReview(value);
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to review email lookup",
          );
      });
    return () => controller.abort();
  }, [runId, revision]);

  async function confirm() {
    if (!review || !selected.length || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    const selection = JSON.stringify([selected.toSorted(), review.revision]);
    if (request.current?.selection !== selection)
      request.current = { selection, id: crypto.randomUUID() };
    try {
      const response = await api<{ run: { id: string } }>(
        `discovery/${runId}/emails`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            candidate_ids: selected,
            estimated_credits: selected.length,
            revision: review.revision,
            request_id: request.current.id,
          }),
        },
      );
      router.push(`/find-leads/${response.run.id}`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to start email lookup",
      );
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="live-email-review" aria-labelledby="email-review-title">
      <h2 ref={heading} id="email-review-title" tabIndex={-1}>
        Find emails
      </h2>
      <p className="settings-help">
        Nothing is charged yet. Pick people, then confirm the cost.
      </p>
      {!review && !error && <p role="status">Loading leads…</p>}
      {review && (
        <>
          <fieldset disabled={busy}>
            <legend className="sr-only">
              People to find emails for
            </legend>
            {review.items.map((lead) => (
              <label className="live-email-choice" key={lead.id}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(lead.id)}
                  onChange={(event) =>
                    setSelected((old) =>
                      event.target.checked
                        ? [...old, lead.id]
                        : old.filter((id) => id !== lead.id),
                    )
                  }
                />
                <span>
                  <strong>{lead.name}</strong>
                  <span>
                    {[lead.title, lead.company].filter(Boolean).join(" · ")}
                  </span>
                </span>
              </label>
            ))}
            {!review.items.length && (
              <p>
                No eligible profiles. People with emails, deleted contacts and
                past lookups are skipped. Only this run counts.
              </p>
            )}
          </fieldset>
          <p className="live-cost" aria-live="polite">
            {review?.provider_name ?? "BetterContact"} email cost:{" "}
            <strong>
              up to {selected.length} credit{selected.length === 1 ? "" : "s"}
            </strong>
          </p>
          <p className="settings-help">
            {review.note} Some people may have no email.
          </p>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="live-actions">
        <button
          className="button primary"
          disabled={!review || !selected.length || busy}
          onClick={confirm}
        >
          {busy ? "Starting…" : "Confirm & find emails"}
        </button>
        <button className="button" disabled={busy} onClick={close}>
          Cancel
        </button>
        {error && (
          <button
            className="button"
            disabled={busy}
            onClick={() => setRevision((value) => value + 1)}
          >
            Refresh review
          </button>
        )}
      </div>
    </section>
  );
}
