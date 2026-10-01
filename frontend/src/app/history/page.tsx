"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Info, MessageSquare, Search, Trash2 } from "lucide-react";
import PageHeader from "@/components/ui/PageHeader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import { api, errorMessage } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { formatRelative } from "@/lib/utils";

const PAGE = 15;

type Result = { search: string; items: Conversation[]; total: number };

export default function HistoryPage() {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Wait for a short pause in typing before asking the server
  useEffect(() => {
    const timer = setTimeout(() => setSearch(input.trim()), 300);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    let cancelled = false;
    api
      .listConversations({ q: search, limit: PAGE, offset: 0 })
      .then((page) => {
        if (cancelled) return;
        setResult({ search, items: page.items, total: page.total });
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [search, attempt]);

  const loading = result === null || result.search !== search;
  const items = !loading && result ? result.items : [];
  const total = !loading && result ? result.total : 0;

  async function loadMore() {
    if (!result) return;
    setLoadingMore(true);
    try {
      const page = await api.listConversations({ q: search, limit: PAGE, offset: result.items.length });
      setResult((prev) =>
        prev && prev.search === search
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

  async function remove(id: string) {
    if (
      !window.confirm(
        "Delete this conversation? The anonymised query log is kept to help improve the system."
      )
    )
      return;
    try {
      await api.deleteConversation(id);
      setResult((prev) =>
        prev ? { ...prev, items: prev.items.filter((c) => c.id !== id), total: Math.max(0, prev.total - 1) } : prev
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      <PageHeader
        title="History"
        description="Reopen any past conversation and continue where you left off."
      />

      <div className="mb-4 flex items-start gap-3 rounded-2xl border border-octo-green/20 bg-octo-green-soft px-5 py-4 text-sm leading-relaxed text-octo-green-dark">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Every question, generated query, result summary and feedback rating is logged to help improve the
          agent. See how it is doing on the{" "}
          <Link href="/insights" className="font-medium underline">
            Insights
          </Link>{" "}
          page.
        </span>
      </div>

      <div className="relative mb-5">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Search titles, datasets and messages…"
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-11 pr-4 text-sm text-slate-800 placeholder:text-slate-400 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
        />
      </div>

      {error && (
        <div className="mb-4">
          <ErrorBanner
            message={error}
            onRetry={() => {
              setError(null);
              setAttempt((a) => a + 1);
            }}
          />
        </div>
      )}

      {!error && loading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
          {search ? (
            "No conversations match your search."
          ) : (
            <>
              No conversations yet.{" "}
              <Link href="/chat" className="font-medium text-octo-green hover:text-octo-green-dark">
                Start one in Chat
              </Link>
              .
            </>
          )}
        </p>
      )}

      {!loading && items.length > 0 && (
        <>
          <div className="space-y-3">
            {items.map((c) => (
              <div
                key={c.id}
                className="group flex items-center gap-2 rounded-2xl border border-slate-200 bg-white pr-3 shadow-sm transition-colors hover:border-octo-green/50"
              >
                <Link
                  href={`/chat?dataset=${c.datasetId}&conversation=${c.id}`}
                  className="flex min-w-0 flex-1 items-center justify-between gap-4 px-5 py-4"
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500 sm:flex">
                      <MessageSquare className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">{c.title}</p>
                      <p className="mt-0.5 truncate text-sm text-slate-500">{c.preview}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-600">
                          {c.datasetName}
                        </span>
                        <span>{c.messageCount} messages</span>
                        <span>·</span>
                        <span>{formatRelative(c.updatedAt)}</span>
                      </div>
                    </div>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-octo-green opacity-80 group-hover:opacity-100">
                    <span className="hidden sm:inline">Continue</span>
                    <ArrowRight className="h-4 w-4" />
                  </span>
                </Link>
                <button
                  onClick={() => remove(c.id)}
                  aria-label="Delete conversation"
                  className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>

          <div className="mt-5 flex flex-col items-center gap-3">
            <p className="text-xs text-slate-400">
              Showing {items.length} of {total}
            </p>
            {items.length < total && (
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