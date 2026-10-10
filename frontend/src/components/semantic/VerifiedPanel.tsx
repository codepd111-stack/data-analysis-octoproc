import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, CircleCheck, Trash2 } from "lucide-react";
import Skeleton from "@/components/ui/Skeleton";
import { api, errorMessage } from "@/lib/api";
import type { VerifiedQuery } from "@/lib/types";
import { formatRelative } from "@/lib/utils";

/** Calculations a person confirmed with a thumbs-up in chat, with a way to retire them. */
export default function VerifiedPanel({ datasetId }: { datasetId: string }) {
  const [items, setItems] = useState<VerifiedQuery[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listVerified(datasetId)
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  async function remove(id: string) {
    const previous = items;
    setItems((prev) => (prev ? prev.filter((v) => v.id !== id) : prev));
    try {
      await api.deleteVerified(datasetId, id);
    } catch (e) {
      setItems(previous);
      setError(errorMessage(e));
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <CircleCheck className="h-4 w-4 text-octo-green" /> Verified answers
      </h2>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-500">
        Calculations a person confirmed with a thumbs-up in chat. The same question is answered
        from here without the AI, and similar questions use them as worked examples. Remove any
        that no longer hold.
      </p>

      {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
      {items === null && !error && <Skeleton className="mt-4 h-16" />}
      {items && items.length === 0 && (
        <p className="mt-4 rounded-xl border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">
          None yet. Give a good answer a thumbs-up in chat to save its calculation here.
        </p>
      )}

      {items && items.length > 0 && (
        <div className="mt-4 space-y-2">
          {items.map((v) => (
            <div key={v.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium text-slate-900">{v.question}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {formatRelative(v.createdAt)}
                    {!v.standalone && " · follow-up question, used as an example only"}
                    {v.conversationId && (
                      <>
                        {" · "}
                        <Link
                          to={`/chat?dataset=${datasetId}&conversation=${v.conversationId}`}
                          className="font-medium text-octo-green hover:text-octo-green-dark"
                        >
                          Open conversation
                        </Link>
                      </>
                    )}
                  </p>
                </div>
                <button
                  onClick={() => remove(v.id)}
                  aria-label="Remove verified answer"
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <details className="group mt-2">
                <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700">
                  SQL
                  <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-white px-3 py-2 font-mono text-xs leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200">
                  {v.sql}
                </pre>
              </details>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
