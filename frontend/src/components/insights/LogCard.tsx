import Link from "next/link";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import type { LogEntry, LogStatus } from "@/lib/types";
import { cn, formatRelative } from "@/lib/utils";

const STATUS: Record<LogStatus, { label: string; classes: string }> = {
  ok: { label: "Answered", classes: "bg-octo-green-soft text-octo-green-dark ring-octo-green/30" },
  retried: { label: "Retried", classes: "bg-amber-50 text-amber-700 ring-amber-200" },
  failed: { label: "Failed", classes: "bg-rose-50 text-rose-700 ring-rose-200" },
  unanswerable: { label: "Unanswerable", classes: "bg-slate-100 text-slate-600 ring-slate-200" },
  rate_limited: { label: "Rate limited", classes: "bg-sky-50 text-sky-700 ring-sky-200" },
};

const REASON_LABEL: Record<string, string> = {
  wrong_numbers: "Wrong numbers",
  wrong_chart: "Wrong chart",
  misunderstood: "Misunderstood",
  too_vague: "Too vague",
  other: "Other",
};

export default function LogCard({ log }: { log: LogEntry }) {
  const status = STATUS[log.status];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="min-w-0 flex-1 break-words text-sm font-medium text-slate-900">{log.question}</p>
        <span
          className={cn(
            "inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
            status.classes
          )}
        >
          {status.label}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
        {log.datasetName && (
          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-600">{log.datasetName}</span>
        )}
        <span>{formatRelative(log.createdAt)}</span>
        <span>
          {log.attempts} attempt{log.attempts === 1 ? "" : "s"}
        </span>
        {log.latencyMs != null && <span>{(log.latencyMs / 1000).toFixed(1)} s</span>}
        {log.rowCount != null && <span>{log.rowCount} rows</span>}
        {log.model && <span className="font-mono">{log.model}</span>}
        {log.feedback === "up" && (
          <span className="inline-flex items-center gap-1 text-octo-green">
            <ThumbsUp className="h-3.5 w-3.5" /> Helpful
          </span>
        )}
        {log.feedback === "down" && (
          <span className="inline-flex items-center gap-1 text-rose-600">
            <ThumbsDown className="h-3.5 w-3.5" />
            {log.feedbackReason ? (REASON_LABEL[log.feedbackReason] ?? log.feedbackReason) : "Not helpful"}
          </span>
        )}
      </div>

      {log.error && (
        <p className="mt-3 break-words rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs leading-relaxed text-slate-600">
          {log.error}
        </p>
      )}

      {log.sql && (
        <details className="mt-3 rounded-xl border border-slate-200">
          <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-slate-500 hover:text-slate-700">
            SQL
          </summary>
          <pre className="overflow-x-auto border-t border-slate-100 bg-slate-50 px-4 py-3 font-mono text-xs leading-relaxed text-slate-700">
            {log.sql}
          </pre>
        </details>
      )}

      {log.conversationId && log.datasetId && (
        <Link
          href={`/chat?dataset=${log.datasetId}&conversation=${log.conversationId}`}
          className="mt-3 inline-block text-xs font-medium text-octo-green hover:text-octo-green-dark"
        >
          Open conversation
        </Link>
      )}
    </div>
  );
}