"use client";
import { useEffect, useRef, useState } from "react";
import type { Account } from "@/lib/auth";
import { WorkspacePage } from "@/components/workspace-records";
import { useProductTour } from "@/components/product-tour-provider";

/** Entry point only; the walkthrough runs over the existing product pages. */
export default function Tour({ user }: { user: Account }) {
  const tour = useProductTour();
  const requested = useRef(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!tour || requested.current) return;
    requested.current = true;
    void tour.start(user).catch((caught) => {
      requested.current = false;
      setError(caught instanceof Error ? caught.message : "Could not open the tour.");
    });
  }, [tour?.start, user, retry]);
  return <WorkspacePage user={user} active="tour" title="Product tour" description="A quick guided look at LeadZen.">
    <section className="panel"><p role={error ? "alert" : "status"}>{error || "Opening the tour…"}</p>
      {error && <button className="button" type="button" onClick={() => { setError(""); setRetry((value) => value + 1); }}>Try again</button>}
    </section>
  </WorkspacePage>;
}
