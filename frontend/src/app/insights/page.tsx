"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import PageHeader from "@/components/ui/PageHeader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import LogCard from "@/components/insights/LogCard";
import { api, errorMessage } from "@/lib/api";
import type { InsightsSummary, LogEntry } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";

const FILTERS = [
  { value: "attention", label: "Needs attention" },
  { value: "failed", label: "Failed" },
  { value: "downvoted", label: "Downvoted" },
  { value: "retried", label: "Retried" },
  { value: "unanswerable", label: "Unanswerable" },
  { value: "all", label: "All" },
] as const;

type FilterValue = (typeof FILTERS)[number]["value"];

const WINDOWS = [
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
  { label: "Last 90 days", value: 90 },
  { label: "All time", value: 0 },
];

const PAGE = 15;

type SummaryState = { key: number; data: InsightsSummary };
type LogsState = { key: string; items: LogEntry[]; total: number };

export default function InsightsPage() {
  const [filter, setFilter] = useState<FilterValue>("attention");
  const [windowDays, setWindowDays] = useState(30);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [logs, setLogs] = useState<LogsState | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exporting, setExporting] = useState(false);

  const logsKey = `${filter}|${windowDays}`;

  useEffect(() => {
    let cancelled = false;
    api
      .getInsights(windowDays || undefined)
      .then((data) => {
        if (cancelled) return;
        setSummary({ key: windowDays, data });
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [windowDays, attempt]);

  useEffect(() => {
    let cancelled = false;
    api
      .listLogs({ filter, days: windowDays || undefined, limit: PAGE, offset: 0 })
      .then((page) => {
        if (cancelled) return;
        setLogs({ key: `${filter}|${windowDays}`, items: page.items, total: page.total });
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [filter, windowDays, attempt]);

  const summaryReady = summary !== null && summary.key === windowDays;
  const logsReady = logs !== null && logs.key === logsKey;
  const s = summaryReady ? summary.data : null;

  async function loadMore() {
    if (!logs) return;
    setLoadingMore(true);
    try {
      const page = await api.listLogs({
        filter,
        days: windowDays || undefined,
        limit: PAGE,
        offset: logs.items.length,
      });
      setLogs((prev) =>
        prev && prev.key === logsKey
          ? {
              ...prev,
              items: [...prev.items, ...page.items.filter((n) => !prev.items.some((o) => o.id === n.id))],
              total: page.total,
            }
          : prev
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoadingMore(false);
    }
  }

  async function downloadCsv() {
    setExporting(true);
    try {
      const blob = await api.exportLogs(filter, windowDays || undefined);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "octoproc-query-logs.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setExporting(false);
    }
  }

  const helpfulTotal = s ? s.thumbsUp + s.thumbsDown : 0;
  const cards = s
    ? [
        { label: "Questions asked", value: formatNumber(s.total) },
        {
          label: "Answered",
          value: s.total ? `${Math.round((100 * s.answered) / s.total)}%` : "–",
          sub: `${formatNumber(s.answered)} of ${formatNumber(s.total)}`,
        },
        {
          label: "Avg. response time",
          value: s.avgLatencyMs != null ? `${(s.avgLatencyMs / 1000).toFixed(1)} s` : "–",
        },
        {
          label: "Rated helpful",
          value: helpfulTotal ? `${Math.round((100 * s.thumbsUp) / helpfulTotal)}%` : "–",
          sub: `${s.thumbsUp} up · ${s.thumbsDown} down`,
        },
        { label: "Failed", value: formatNumber(s.failed), bad: s.failed > 0 },
        { label: "Needed retries", value: formatNumber(s.retried) },
        { label: "Unanswerable", value: formatNumber(s.unanswerable), sub: "data can't answer it" },
        { label: "Rate limited", value: formatNumber(s.rateLimited), sub: "AI service busy" },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Insights"
        description="See where the agent struggles: failed queries, downvoted answers and questions the data can't answer. Use this to improve prompts and the semantic layers."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
            >
              {WINDOWS.map((w) => (
                <option key={w.value} value={w.value}>
                  {w.label}
                </option>
              ))}
            </select>
            <button
              onClick={downloadCsv}
              disabled={exporting}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <Download className="h-4 w-4" /> {exporting ? "Exporting…" : "Export CSV"}
            </button>
          </div>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBanner
            message={error}
            onRetry={() => {
              setError(null);
              setAttempt((a) => a + 1);
            }}
          />
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {!s &&
          !error &&
          [0, 1, 2, 3, 4, 5, 6, 7].map((i) => <Skeleton key={i} className="h-24" />)}
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <p className={cn("text-2xl font-semibold", c.bad ? "text-rose-600" : "text-slate-900")}>
              {c.value}
            </p>
            <p className="text-sm text-slate-500">{c.label}</p>
            {c.sub && <p className="mt-0.5 text-xs text-slate-400">{c.sub}</p>}
          </div>
        ))}
      </div>

      {/* Top errors */}
      {s && s.topErrors.length > 0 && (
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Most common failures</h2>
          <ul className="mt-3 space-y-2">
            {s.topErrors.map((e) => (
              <li key={e.error} className="flex items-start justify-between gap-4 text-sm">
                <span className="min-w-0 break-words font-mono text-xs leading-relaxed text-slate-600">
                  {e.error}
                </span>
                <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  ×{e.count}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Filter tabs */}
      <div className="mb-4 mt-8 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
              filter === f.value
                ? "bg-octo-green text-white"
                : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <p className="mb-4 text-xs text-slate-400">
        Tip: export the &quot;Needs attention&quot; rows and use them to refine the prompts in
        services/prompts.py and the descriptions in your semantic layers.
      </p>

      {/* Log list */}
      {!logsReady && !error && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {logsReady && logs.items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
          Nothing here for this filter and period.
        </p>
      )}

      {logsReady && logs.items.length > 0 && (
        <>
          <div className="space-y-3">
            {logs.items.map((log) => (
              <LogCard key={log.id} log={log} />
            ))}
          </div>
          <div className="mt-5 flex flex-col items-center gap-3">
            <p className="text-xs text-slate-400">
              Showing {logs.items.length} of {logs.total}
            </p>
            {logs.items.length < logs.total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </>
      )}
    </>
  );
}