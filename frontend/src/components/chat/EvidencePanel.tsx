import type { ReactNode } from "react";
import { ChevronDown, Code, ShieldCheck, Table, TriangleAlert } from "lucide-react";
import type { ChatMessage, FilterUse } from "@/lib/types";
import TrustBadge from "./TrustBadge";

function cell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "–";
  if (typeof value === "number") return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value;
}

function filterLabel(f: FilterUse) {
  return f.description || f.expression;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-slate-400">{label}</dt>
      <dd className="min-w-0 space-y-1">{children}</dd>
    </>
  );
}

/** The receipts behind an answer: badge, definitions used, the result rows and the SQL. */
export default function EvidencePanel({ message }: { message: ChatMessage }) {
  const g = message.grounding;
  if (!g && !message.sql) return null;

  const hasDefinitions =
    g &&
    (g.metricsUsed.length > 0 ||
      g.filtersApplied.length > 0 ||
      g.filtersSkipped.length > 0 ||
      g.unmatchedAggregates.length > 0);

  return (
    <details className="group rounded-xl border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-500 hover:text-slate-700">
        <ShieldCheck className="h-3.5 w-3.5" />
        Evidence
        {message.trust && <TrustBadge trust={message.trust} size="xs" />}
        <ChevronDown className="ml-auto h-4 w-4 transition-transform group-open:rotate-180" />
      </summary>

      <div className="space-y-4 border-t border-slate-100 px-4 py-3 text-xs text-slate-600">
        {g && <p className="text-sm leading-relaxed text-slate-700">{g.reason}</p>}

        {g && g.filtersMissing.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Not applied: {g.filtersMissing.map(filterLabel).join("; ")}. Ask again, or add the
              rule to the question, to get a governed answer.
            </span>
          </div>
        )}

        {hasDefinitions && g && (
          <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[auto_1fr]">
            {g.metricsUsed.length > 0 && (
              <Row label="Metrics used">
                {g.metricsUsed.map((m) => (
                  <div key={m.name}>
                    <span className="font-medium text-slate-700">{m.name}</span>{" "}
                    <span className="font-mono text-slate-500">= {m.expression}</span>
                  </div>
                ))}
              </Row>
            )}
            {g.filtersApplied.length > 0 && (
              <Row label="Filters applied">
                {g.filtersApplied.map((f) => (
                  <div key={f.id}>
                    <span className="text-slate-700">{filterLabel(f)}</span>{" "}
                    <span className="font-mono text-slate-500">({f.expression})</span>
                  </div>
                ))}
              </Row>
            )}
            {g.filtersSkipped.length > 0 && (
              <Row label="Filters left out">
                {g.filtersSkipped.map((f) => (
                  <div key={f.id}>
                    <span className="text-slate-700">{filterLabel(f)}</span>
                    {f.reason && <span className="text-slate-500"> — {f.reason}</span>}
                  </div>
                ))}
              </Row>
            )}
            {g.unmatchedAggregates.length > 0 && (
              <Row label="Not governed">
                <span className="font-mono text-slate-700">{g.unmatchedAggregates.join(", ")}</span>
              </Row>
            )}
          </dl>
        )}

        {g && g.rowsPreview.length > 0 && (
          <div>
            <p className="mb-1.5 flex items-center gap-1.5 font-medium text-slate-500">
              <Table className="h-3.5 w-3.5" />
              Result rows
              {g.rowCount > g.rowsPreview.length
                ? ` (first ${g.rowsPreview.length} of ${g.rowCount})`
                : ` (${g.rowCount})`}
              {g.tables.length > 0 && ` from ${g.tables.join(", ")}`}
            </p>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500">
                    {g.columns.map((c) => (
                      <th key={c} className="whitespace-nowrap px-3 py-1.5 font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {g.rowsPreview.map((row, i) => (
                    <tr key={i}>
                      {g.columns.map((c) => (
                        <td key={c} className="whitespace-nowrap px-3 py-1.5 font-mono text-slate-700">
                          {cell(row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {message.sql && (
          <div>
            <p className="mb-1.5 flex items-center gap-1.5 font-medium text-slate-500">
              <Code className="h-3.5 w-3.5" /> SQL that produced it
            </p>
            <pre className="overflow-x-auto rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs leading-relaxed text-slate-700">
              {message.sql}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}
