import Link from "next/link";
import { ArrowRight, FileSpreadsheet, RotateCcw, TriangleAlert } from "lucide-react";
import type { Dataset } from "@/lib/types";
import { formatNumber, formatRelative } from "@/lib/utils";
import StatusBadge from "@/components/ui/StatusBadge";

export default function DatasetCard({
  dataset,
  onRetry,
}: {
  dataset: Dataset;
  onRetry?: (id: string) => void;
}) {
  const { status } = dataset;
  const hasStats = status !== "failed" && status !== "processing";

  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
            <FileSpreadsheet className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{dataset.name}</p>
            <p className="truncate text-xs text-slate-500">
              {dataset.fileName}
              {(dataset.tableCount ?? 1) > 1 ? ` · ${dataset.tableCount} tables` : ""}
            </p>
          </div>
        </div>
        <StatusBadge status={status} />
      </div>

      <dl className="mt-5 grid grid-cols-3 gap-2 text-center">
        {[
          { label: "Rows", value: hasStats ? formatNumber(dataset.rows) : "–" },
          { label: "Columns", value: hasStats ? String(dataset.columns) : "–" },
          { label: "Size", value: dataset.sizeLabel },
        ].map((s) => (
          <div key={s.label} className="rounded-lg bg-slate-50 px-2 py-2">
            <dd className="text-sm font-semibold text-slate-900">{s.value}</dd>
            <dt className="text-[11px] uppercase tracking-wide text-slate-400">{s.label}</dt>
          </div>
        ))}
      </dl>

      {status === "processing" && (
        <div className="mt-5">
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-slate-600">{dataset.stage ?? "Processing"}</span>
            <span className="font-medium text-slate-700">{dataset.progress ?? 0}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-octo-green transition-all duration-500"
              style={{ width: `${dataset.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {status === "failed" && (
        <div className="mt-5 flex gap-2 rounded-lg bg-rose-50 p-3 text-xs leading-relaxed text-rose-700">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          {dataset.error ?? "Processing failed."}
        </div>
      )}

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
        <span className="text-xs text-slate-400">Uploaded {formatRelative(dataset.uploadedAt)}</span>

        {status === "needs_review" && (
          <Link
            href={`/review/${dataset.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-octo-green hover:text-octo-green-dark"
          >
            Review <ArrowRight className="h-4 w-4" />
          </Link>
        )}
        {status === "approved" && (
          <div className="flex items-center gap-4">
            <Link
              href={`/review/${dataset.id}`}
              className="text-sm font-medium text-slate-500 hover:text-slate-700"
            >
              Semantics
            </Link>
            <Link
              href={`/chat?dataset=${dataset.id}`}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-octo-green hover:text-octo-green-dark"
            >
              Chat <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        )}
        {status === "failed" && (
          <button
            onClick={() => onRetry?.(dataset.id)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <RotateCcw className="h-4 w-4" /> Retry
          </button>
        )}
      </div>
    </div>
  );
}