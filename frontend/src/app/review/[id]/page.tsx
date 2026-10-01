"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CircleCheck,
  Link2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import ColumnTable from "@/components/semantic/ColumnTable";
import { api, errorMessage } from "@/lib/api";
import type { ColumnSemantic, Dataset, Relationship, SemanticLayer } from "@/lib/types";
import { cn, uid } from "@/lib/utils";
import QualityPanel from "@/components/semantic/QualityPanel";

const inputClasses =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20";

type Busy = "draft" | "approve" | "regenerate" | null;

function BackLink() {
  return (
    <Link
      href="/review"
      className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
    >
      <ArrowLeft className="h-4 w-4" /> All datasets
    </Link>
  );
}

export default function ReviewEditorPage() {
  const { id } = useParams<{ id: string }>();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [layer, setLayer] = useState<SemanticLayer | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [relDraft, setRelDraft] = useState<{ from: string; to: string; type: Relationship["type"] }>({
    from: "",
    to: "",
    type: "many-to-one",
  });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [ds, semantic] = await Promise.all([api.getDataset(id), api.getSemantic(id)]);
        if (cancelled) return;
        setDataset(ds);
        setLayer(semantic);
      } catch (e) {
        if (!cancelled) setLoadError(errorMessage(e));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  function edit(fn: (l: SemanticLayer) => SemanticLayer) {
    setLayer((prev) => (prev ? fn(prev) : prev));
    setDirty(true);
    setNotice(null);
  }

  function updateColumn(tableName: string, columnName: string, patch: Partial<ColumnSemantic>) {
    edit((l) => ({
      ...l,
      tables: l.tables.map((t) =>
        t.name !== tableName
          ? t
          : {
              ...t,
              columns: t.columns.map((c) => (c.name !== columnName ? c : { ...c, ...patch })),
            }
      ),
    }));
  }

  function updateTableDescription(tableName: string, description: string) {
    edit((l) => ({
      ...l,
      tables: l.tables.map((t) => (t.name === tableName ? { ...t, description } : t)),
    }));
  }

  function removeRelationship(relId: string) {
    edit((l) => ({ ...l, relationships: l.relationships.filter((r) => r.id !== relId) }));
  }

  function addRelationship() {
    const { from, to, type } = relDraft;
    if (!from || !to || from.split(".")[0] === to.split(".")[0]) return;
    edit((l) => ({
      ...l,
      relationships: [...l.relationships, { id: uid(), from, to, type }],
    }));
    setRelDraft({ from: "", to: "", type: "many-to-one" });
  }

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  async function saveDraft() {
    if (!layer || !dataset) return;
    setBusy("draft");
    setActionError(null);
    try {
      const saved = await api.saveSemantic(id, layer);
      setLayer(saved);
      setDirty(false);
      setSavedAt(timeNow());
      if (dataset.status === "approved") {
        setNotice(
          "Draft saved. Chat keeps using the last approved version until you approve again."
        );
      }
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (!layer) return;
    setBusy("approve");
    setActionError(null);
    try {
      // Approval applies to the latest saved version, so save any edits first
      if (dirty) {
        const saved = await api.saveSemantic(id, layer);
        setLayer(saved);
      }
      const updated = await api.approveDataset(id);
      setDataset(updated);
      setDirty(false);
      setNotice(null);
      setSavedAt(timeNow());
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function regenerate() {
    if (!dataset) return;
    if (
      dirty &&
      !window.confirm("Regenerating replaces your unsaved edits with a fresh AI draft. Continue?")
    )
      return;
    setBusy("regenerate");
    setActionError(null);
    try {
      const fresh = await api.regenerateSemantic(id);
      setLayer(fresh);
      setDirty(false);
      setSavedAt(timeNow());
      setNotice(
        dataset.status === "approved"
          ? "A new draft was generated. Chat keeps using the last approved version until you approve again."
          : null
      );
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  if (loadError) {
    return (
      <>
        <BackLink />
        <ErrorBanner
          message={loadError}
          onRetry={() => {
            setLoadError(null);
            setAttempt((a) => a + 1);
          }}
        />
      </>
    );
  }

  if (!dataset || !layer) {
    return (
      <>
        <BackLink />
        <Skeleton className="mb-6 h-16 w-1/2" />
        <Skeleton className="mb-6 h-32" />
        <Skeleton className="h-96" />
      </>
    );
  }

  const approved = dataset.status === "approved";
  const columnOptions = layer.tables.flatMap((t) => t.columns.map((c) => `${t.name}.${c.name}`));
  const draftValid =
    relDraft.from !== "" &&
    relDraft.to !== "" &&
    relDraft.from.split(".")[0] !== relDraft.to.split(".")[0];

  return (
    <>
      <BackLink />

      <PageHeader
        title={dataset.name}
        description="Review the generated semantic layer. Edit anything that looks wrong; the chat agent will rely on exactly what you approve here."
        actions={<StatusBadge status={dataset.status} />}
      />

      {approved && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-octo-green/30 bg-octo-green-soft px-5 py-4">
          <div className="flex items-center gap-3 text-sm text-octo-green-dark">
            <CircleCheck className="h-5 w-5" />
            Approved. This dataset is available in chat.
          </div>
          <Link
            href={`/chat?dataset=${dataset.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-octo-green-dark hover:underline"
          >
            Start chatting <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {notice && (
        <div className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          {notice}
        </div>
      )}

      {layer.generatedBy === "llm" ? (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-octo-green/20 bg-octo-green-soft px-5 py-4 text-sm leading-relaxed text-octo-green-dark">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Drafted by AI from column names, statistics and a few sample values (never the full data;
            sensitive-looking columns such as email or phone are not sampled). Please check it before
            approving.
          </span>
        </div>
      ) : (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-relaxed text-amber-800">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            This draft was guessed from column names only; the AI step did not run. Check the
            GROQ_API_KEY and rate limits on the backend, then use Regenerate with AI.
          </span>
        </div>
      )}
      <QualityPanel datasetId={dataset.id} />
      {/* Summary */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">Dataset summary</h2>
          <button
            onClick={regenerate}
            disabled={busy !== null}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", busy === "regenerate" && "animate-spin")} />
            {busy === "regenerate" ? "Regenerating…" : "Regenerate with AI"}
          </button>
        </div>
        <textarea
          value={layer.summary}
          rows={3}
          onChange={(e) => edit((l) => ({ ...l, summary: e.target.value }))}
          className={`${inputClasses} mt-3 resize-none leading-relaxed`}
        />
      </section>

      {/* Tables */}
      {layer.tables.map((table) => (
        <section
          key={table.name}
          className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="font-mono text-sm font-semibold text-slate-900">{table.name}</h2>
            <input
              value={table.description}
              onChange={(e) => updateTableDescription(table.name, e.target.value)}
              className={`${inputClasses} mt-2`}
            />
          </div>
          <ColumnTable
            columns={table.columns}
            onChange={(columnName, patch) => updateColumn(table.name, columnName, patch)}
          />
        </section>
      ))}

      {/* Relationships */}
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Relationships</h2>
        <div className="mt-3 space-y-2">
          {layer.relationships.length === 0 && (
            <p className="text-sm text-slate-500">
              {layer.tables.length > 1
                ? "No relationships found between these tables. You can add one below."
                : "This dataset has a single table, so there is nothing to relate."}
            </p>
          )}
          {layer.relationships.map((r) => (
            <div
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Link2 className="h-4 w-4 text-slate-400" />
                <span className="font-mono text-[13px] text-slate-800">{r.from}</span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-mono text-[13px] text-slate-800">{r.to}</span>
                <span className="rounded-md bg-white px-2 py-0.5 text-xs text-slate-500 ring-1 ring-inset ring-slate-200">
                  {r.type}
                </span>
              </div>
              <button
                onClick={() => removeRelationship(r.id)}
                aria-label="Remove relationship"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        {layer.tables.length > 1 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
            <select
              value={relDraft.from}
              onChange={(e) => setRelDraft({ ...relDraft, from: e.target.value })}
              className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-1.5 font-mono text-xs text-slate-700 focus:border-octo-green focus:outline-none"
            >
              <option value="">child column…</option>
              {columnOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={relDraft.to}
              onChange={(e) => setRelDraft({ ...relDraft, to: e.target.value })}
              className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-1.5 font-mono text-xs text-slate-700 focus:border-octo-green focus:outline-none"
            >
              <option value="">parent column…</option>
              {columnOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <select
              value={relDraft.type}
              onChange={(e) =>
                setRelDraft({ ...relDraft, type: e.target.value as Relationship["type"] })
              }
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 focus:border-octo-green focus:outline-none"
            >
              <option value="many-to-one">many-to-one</option>
              <option value="one-to-many">one-to-many</option>
              <option value="one-to-one">one-to-one</option>
            </select>
            <button
              onClick={addRelationship}
              disabled={!draftValid}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" /> Add
            </button>
          </div>
        )}
      </section>

      {actionError && (
        <div className="mt-6">
          <ErrorBanner message={actionError} />
        </div>
      )}

      {/* Sticky action bar */}
      <div className="sticky bottom-4 z-10 mt-8 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 px-5 py-4 shadow-lg backdrop-blur">
        <p className="text-sm text-slate-500">
          {dirty ? "You have unsaved changes." : savedAt ? `Saved at ${savedAt}.` : "No changes yet."}
        </p>
        <div className="flex gap-3">
          <button
            onClick={saveDraft}
            disabled={!dirty || busy !== null}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "draft" ? "Saving…" : "Save draft"}
          </button>
          <button
            onClick={approve}
            disabled={busy !== null}
            className="rounded-lg bg-octo-green px-4 py-2 text-sm font-medium text-white hover:bg-octo-green-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "approve"
              ? "Approving…"
              : approved
                ? dirty
                  ? "Save & keep approved"
                  : "Approve this version"
                : "Approve for chat"}
          </button>
        </div>
      </div>
    </>
  );
}