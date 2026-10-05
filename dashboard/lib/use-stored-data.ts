"use client";
import { useCallback, useEffect, useState } from "react";
import { useWorkspaceRevision } from "@/lib/workspace-updates";
import { api } from "@/lib/client-api";

export function useStoredData<T>(path: string, pollMs = 0) {
  const workspaceRevision = useWorkspaceRevision();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    setLoading(true);
    function load() {
      if (inFlight || controller.signal.aborted) return;
      inFlight = true;
      void api<T>(path, { signal: controller.signal }).then((result) => {
        if (!controller.signal.aborted) { setData(result); setError(""); }
      }).catch((caught) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to load saved data");
      }).finally(() => {
        inFlight = false;
        if (!controller.signal.aborted) setLoading(false);
      });
    }
    void load();
    const timer = pollMs ? window.setInterval(() => { if (!document.hidden) void load(); }, pollMs) : null;
    return () => { controller.abort(); if (timer) window.clearInterval(timer); };
  }, [path, pollMs, revision, workspaceRevision]);
  return { data, setData, loading, error, refresh };
}
