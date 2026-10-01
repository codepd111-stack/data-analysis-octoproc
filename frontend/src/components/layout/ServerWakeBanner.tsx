"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";

type State = "checking" | "waking" | "ok" | "down";

export default function ServerWakeBanner() {
  const [state, setState] = useState<State>("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    // If the first answer is slow, tell the user why
    const slowTimer = setTimeout(() => {
      if (!cancelled) setState((s) => (s === "checking" ? "waking" : s));
    }, 2500);

    async function check() {
      const startedAt = Date.now();
      while (!cancelled) {
        try {
          await api.health();
          if (!cancelled) setState("ok");
          return;
        } catch {
          if (Date.now() - startedAt > 90_000) {
            if (!cancelled) setState("down");
            return;
          }
          if (!cancelled) setState("waking");
          await new Promise((resolve) => setTimeout(resolve, 3000));
        }
      }
    }
    check();

    return () => {
      cancelled = true;
      clearTimeout(slowTimer);
    };
  }, [attempt]);

  if (state === "checking" || state === "ok") return null;

  if (state === "waking") {
    return (
      <div className="mb-6 flex items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800">
        <LoaderCircle className="h-4 w-4 shrink-0 animate-spin" />
        Connecting to the server… free hosting can take up to a minute to start after a quiet period.
      </div>
    );
  }

  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-800">
      <span className="flex items-center gap-3">
        <TriangleAlert className="h-4 w-4 shrink-0" />
        The server isn&apos;t responding.
      </span>
      <button
        onClick={() => {
          setState("checking");
          setAttempt((a) => a + 1);
        }}
        className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
      >
        Try again
      </button>
    </div>
  );
}