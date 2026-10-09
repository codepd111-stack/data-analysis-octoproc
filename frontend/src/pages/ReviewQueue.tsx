import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CircleCheck, ShieldCheck } from "lucide-react";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import { api, errorMessage } from "@/lib/api";
import type { Dataset } from "@/lib/types";

function Row({ dataset }: { dataset: Dataset }) {
  return (
    <Link
      to={`/review/${dataset.id}`}
      className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm transition-colors hover:border-octo-green/50"
    >
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
          {dataset.status === "approved" ? (
            <CircleCheck className="h-5 w-5 text-octo-green" />
          ) : (
            <ShieldCheck className="h-5 w-5" />
          )}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">{dataset.name}</p>
          <p className="truncate text-xs text-slate-500">{dataset.fileName}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-4">
        <StatusBadge status={dataset.status} />
        <ArrowRight className="hidden h-4 w-4 text-slate-400 sm:block" />
      </div>
    </Link>
  );
}

export default function ReviewQueuePage() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .listDatasets()
      .then((d) => {
        if (!cancelled) setDatasets(d);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const pending = (datasets ?? []).filter((d) => d.status === "needs_review");
  const approved = (datasets ?? []).filter((d) => d.status === "approved");

  return (
    <>
      <PageHeader
        title="Semantic Review"
        description="Check what the system understood about each dataset. Fix any column meanings or relationships, then approve to unlock chat."
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => {
            setError(null);
            setAttempt((a) => a + 1);
          }}
        />
      )}

      {!error && datasets === null && (
        <div className="space-y-3">
          <Skeleton className="h-[74px]" />
          <Skeleton className="h-[74px]" />
        </div>
      )}

      {datasets && (
        <>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Awaiting your review ({pending.length})
          </h2>
          <div className="space-y-3">
            {pending.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-8 text-center text-sm text-slate-500">
                Nothing to review right now.
              </p>
            ) : (
              pending.map((d) => <Row key={d.id} dataset={d} />)
            )}
          </div>

          <h2 className="mb-3 mt-10 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Approved ({approved.length})
          </h2>
          <div className="space-y-3">
            {approved.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-8 text-center text-sm text-slate-500">
                No approved datasets yet.
              </p>
            ) : (
              approved.map((d) => <Row key={d.id} dataset={d} />)
            )}
          </div>
        </>
      )}
    </>
  );
}