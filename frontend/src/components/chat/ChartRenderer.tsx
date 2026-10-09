import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "@/lib/types";

const COLORS = ["#008000", "#e60000", "#0ea5e9", "#f59e0b", "#8b5cf6", "#64748b"];

const tooltipStyle = {
  borderRadius: 12,
  border: "1px solid #e2e8f0",
  fontSize: 12,
  boxShadow: "0 4px 12px rgba(15, 23, 42, 0.08)",
};

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const formatTick = (v: number | string) => (typeof v === "number" ? compact.format(v) : String(v));

const axisTick = { fontSize: 12, fill: "#64748b" };

export default function ChartRenderer({ spec }: { spec: ChartSpec }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="mb-3 text-sm font-medium text-slate-900">{spec.title}</p>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {spec.type === "bar" ? (
            <BarChart data={spec.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey={spec.xKey} tick={axisTick} axisLine={false} tickLine={false} minTickGap={16} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} tickFormatter={formatTick} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#f1f5f9" }} />
              {spec.yKeys.length > 1 && <Legend />}
              {spec.yKeys.map((key, i) => (
                <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[6, 6, 0, 0]} maxBarSize={48} />
              ))}
            </BarChart>
          ) : spec.type === "line" ? (
            <LineChart data={spec.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey={spec.xKey} tick={axisTick} axisLine={false} tickLine={false} minTickGap={16} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} tickFormatter={formatTick} />
              <Tooltip contentStyle={tooltipStyle} />
              {spec.yKeys.length > 1 && <Legend />}
              {spec.yKeys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          ) : (
            <PieChart>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Pie
                data={spec.data}
                dataKey={spec.yKeys[0]}
                nameKey={spec.xKey}
                innerRadius={52}
                outerRadius={88}
                paddingAngle={2}
              >
                {spec.data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}