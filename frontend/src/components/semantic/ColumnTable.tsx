import type { ColumnRole, ColumnSemantic } from "@/lib/types";

const ROLES: ColumnRole[] = ["identifier", "dimension", "measure", "date"];

export default function ColumnTable({
  columns,
  onChange,
}: {
  columns: ColumnSemantic[];
  onChange: (columnName: string, patch: Partial<ColumnSemantic>) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
            <th className="px-5 py-3 font-medium">Column</th>
            <th className="px-3 py-3 font-medium">Type</th>
            <th className="px-3 py-3 font-medium">Role</th>
            <th className="w-[38%] px-3 py-3 font-medium">Business meaning</th>
            <th className="px-3 py-3 font-medium">Nulls</th>
            <th className="px-5 py-3 font-medium">Sample values</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {columns.map((c) => (
            <tr key={c.name} className="align-top">
              <td className="px-5 py-3 font-mono text-[13px] font-medium text-slate-900">{c.name}</td>
              <td className="px-3 py-3">
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
                  {c.dtype}
                </span>
              </td>
              <td className="px-3 py-3">
                <select
                  value={c.role}
                  onChange={(e) => onChange(c.name, { role: e.target.value as ColumnRole })}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-3 py-3">
                <textarea
                  value={c.description}
                  rows={2}
                  onChange={(e) => onChange(c.name, { description: e.target.value })}
                  className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm leading-snug text-slate-700 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
                />
              </td>
              <td className="px-3 py-3 text-xs text-slate-500">{c.nullPct}%</td>
              <td className="px-5 py-3">
                <div className="flex flex-wrap gap-1">
                  {c.samples.map((s) => (
                    <span key={s} className="rounded-md bg-slate-50 px-1.5 py-0.5 text-xs text-slate-500 ring-1 ring-inset ring-slate-200">
                      {s}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}