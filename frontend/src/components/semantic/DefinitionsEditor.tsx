import { useState } from "react";
import { CircleCheck, Filter, ListChecks, Play, Plus, Sigma, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { BusinessRule, DefaultFilter, DefinitionCheck, Metric, SemanticLayer } from "@/lib/types";
import { uid } from "@/lib/utils";

const inputClasses =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20";
const monoClasses = `${inputClasses} font-mono text-[13px]`;
const selectClasses =
  "rounded-lg border border-slate-200 bg-white px-2 py-2 font-mono text-xs text-slate-700 focus:border-octo-green focus:outline-none";
const smallButton =
  "inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

type Definitions = Pick<SemanticLayer, "metrics" | "filters" | "rules">;

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
    >
      <Trash2 className="h-4 w-4" />
    </button>
  );
}

function CheckResult({ result }: { result?: DefinitionCheck }) {
  if (!result) return null;
  if (!result.ok) return <p className="mt-2 text-xs text-rose-600">{result.problem}</p>;
  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-octo-green-dark">
      <CircleCheck className="h-3.5 w-3.5" />
      {result.kind === "metric" ? "Over the whole table, with default filters applied: " : ""}
      <span className="font-mono">{result.value}</span>
    </p>
  );
}

function SectionTitle({ icon: Icon, title, hint }: { icon: typeof Sigma; title: string; hint: string }) {
  return (
    <div className="mb-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        <Icon className="h-4 w-4 text-slate-400" /> {title}
      </h3>
      <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

/**
 * The governed part of the semantic layer: metrics (agreed formulas), default filters (rows to
 * leave out) and business rules. "Check against data" runs each metric and filter for real.
 */
export default function DefinitionsEditor({
  layer,
  datasetId,
  onChange,
}: {
  layer: SemanticLayer;
  datasetId: string;
  onChange: (patch: Partial<Definitions>) => void;
}) {
  const [checks, setChecks] = useState<Record<string, DefinitionCheck>>({});
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  const tables = layer.tables.map((t) => t.name);
  const firstTable = tables[0] ?? "";
  const hasDefinitions = layer.metrics.length + layer.filters.length > 0;

  function change(patch: Partial<Definitions>) {
    setChecks({}); // results describe the previous version
    onChange(patch);
  }

  const updateMetric = (id: string, patch: Partial<Metric>) =>
    change({ metrics: layer.metrics.map((m) => (m.id === id ? { ...m, ...patch } : m)) });
  const updateFilter = (id: string, patch: Partial<DefaultFilter>) =>
    change({ filters: layer.filters.map((f) => (f.id === id ? { ...f, ...patch } : f)) });
  const updateRule = (id: string, patch: Partial<BusinessRule>) =>
    change({ rules: layer.rules.map((r) => (r.id === id ? { ...r, ...patch } : r)) });

  async function check() {
    setChecking(true);
    setCheckError(null);
    try {
      const results = await api.checkDefinitions(datasetId, layer);
      setChecks(Object.fromEntries(results.map((r) => [r.id, r])));
    } catch (e) {
      setCheckError(errorMessage(e));
    } finally {
      setChecking(false);
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <h2 className="text-sm font-semibold text-slate-900">Governed definitions</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-500">
            The agreed formulas and the rows to leave out. The AI copies them exactly into its SQL.
            An answer built only from them is marked <strong>Governed</strong>; anything else is
            marked <strong>Ad-hoc</strong>, so people know when to look closer.
          </p>
        </div>
        <button onClick={check} disabled={checking || !hasDefinitions} className={smallButton}>
          <Play className="h-3.5 w-3.5" /> {checking ? "Checking…" : "Check against data"}
        </button>
      </div>
      {checkError && <p className="mt-3 text-sm text-rose-600">{checkError}</p>}

      {/* Metrics */}
      <div className="mt-6">
        <SectionTitle
          icon={Sigma}
          title="Metrics"
          hint="One aggregate over one table, such as SUM(amount) or COUNT(DISTINCT order_id). Name them the way people ask for them."
        />
        {layer.metrics.length === 0 && (
          <p className="text-sm text-slate-500">
            No metrics yet. Add the numbers people ask for most, such as revenue or order count.
          </p>
        )}
        <div className="space-y-3">
          {layer.metrics.map((m) => (
            <div key={m.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_auto_1.5fr_auto]">
                <input
                  value={m.name}
                  placeholder="Name, e.g. Revenue"
                  onChange={(e) => updateMetric(m.id, { name: e.target.value })}
                  className={inputClasses}
                />
                <select
                  value={m.table}
                  onChange={(e) => updateMetric(m.id, { table: e.target.value })}
                  className={selectClasses}
                >
                  {tables.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  value={m.expression}
                  placeholder="Expression, e.g. SUM(amount)"
                  onChange={(e) => updateMetric(m.id, { expression: e.target.value })}
                  className={monoClasses}
                />
                <RemoveButton
                  label="Remove metric"
                  onClick={() => change({ metrics: layer.metrics.filter((x) => x.id !== m.id) })}
                />
              </div>
              <input
                value={m.description}
                placeholder="What it measures (optional)"
                onChange={(e) => updateMetric(m.id, { description: e.target.value })}
                className={`${inputClasses} mt-2`}
              />
              <CheckResult result={checks[m.id]} />
            </div>
          ))}
        </div>
        <button
          onClick={() =>
            change({
              metrics: [
                ...layer.metrics,
                { id: uid(), name: "", table: firstTable, expression: "", description: "" },
              ],
            })
          }
          className={`${smallButton} mt-3`}
        >
          <Plus className="h-3.5 w-3.5" /> Add metric
        </button>
      </div>

      {/* Default filters */}
      <div className="mt-6 border-t border-slate-100 pt-6">
        <SectionTitle
          icon={Filter}
          title="Default filters"
          hint="A condition that is true for the rows to keep, such as status <> 'test'. Applied to every question unless the user explicitly asks for the other rows."
        />
        {layer.filters.length === 0 && (
          <p className="text-sm text-slate-500">
            No default filters. Add one if the data has test, cancelled or deleted rows that should
            normally be left out.
          </p>
        )}
        <div className="space-y-3">
          {layer.filters.map((f) => (
            <div key={f.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="grid gap-2 sm:grid-cols-[auto_1.5fr_1fr_auto]">
                <select
                  value={f.table}
                  onChange={(e) => updateFilter(f.id, { table: e.target.value })}
                  className={selectClasses}
                >
                  {tables.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  value={f.expression}
                  placeholder="Keep rows where, e.g. status <> 'test'"
                  onChange={(e) => updateFilter(f.id, { expression: e.target.value })}
                  className={monoClasses}
                />
                <input
                  value={f.description}
                  placeholder="Why, e.g. Exclude test orders"
                  onChange={(e) => updateFilter(f.id, { description: e.target.value })}
                  className={inputClasses}
                />
                <RemoveButton
                  label="Remove filter"
                  onClick={() => change({ filters: layer.filters.filter((x) => x.id !== f.id) })}
                />
              </div>
              <CheckResult result={checks[f.id]} />
            </div>
          ))}
        </div>
        <button
          onClick={() =>
            change({
              filters: [...layer.filters, { id: uid(), table: firstTable, expression: "", description: "" }],
            })
          }
          className={`${smallButton} mt-3`}
        >
          <Plus className="h-3.5 w-3.5" /> Add filter
        </button>
      </div>

      {/* Business rules */}
      <div className="mt-6 border-t border-slate-100 pt-6">
        <SectionTitle
          icon={ListChecks}
          title="Business rules"
          hint="Plain-language facts the AI must know, such as “amounts are in EUR including tax” or “the fiscal year starts in April”."
        />
        {layer.rules.length === 0 && <p className="text-sm text-slate-500">No rules yet.</p>}
        <div className="space-y-2">
          {layer.rules.map((r) => (
            <div key={r.id} className="flex items-start gap-2">
              <input
                value={r.text}
                placeholder="A rule the SQL writer must follow"
                onChange={(e) => updateRule(r.id, { text: e.target.value })}
                className={inputClasses}
              />
              <RemoveButton
                label="Remove rule"
                onClick={() => change({ rules: layer.rules.filter((x) => x.id !== r.id) })}
              />
            </div>
          ))}
        </div>
        <button
          onClick={() => change({ rules: [...layer.rules, { id: uid(), text: "" }] })}
          className={`${smallButton} mt-3`}
        >
          <Plus className="h-3.5 w-3.5" /> Add rule
        </button>
      </div>
    </section>
  );
}
