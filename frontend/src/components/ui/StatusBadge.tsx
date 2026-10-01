import type { DatasetStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const config: Record<DatasetStatus, { label: string; classes: string; dot: string }> = {
  processing: { label: "Processing", classes: "bg-slate-100 text-slate-600 ring-slate-200", dot: "bg-slate-400" },
  needs_review: { label: "Needs review", classes: "bg-amber-50 text-amber-700 ring-amber-200", dot: "bg-amber-500" },
  approved: { label: "Ready for chat", classes: "bg-octo-green-soft text-octo-green-dark ring-octo-green/30", dot: "bg-octo-green" },
  failed: { label: "Failed", classes: "bg-rose-50 text-rose-700 ring-rose-200", dot: "bg-rose-500" },
};

export default function StatusBadge({ status }: { status: DatasetStatus }) {
  const c = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        c.classes
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot, status === "processing" && "animate-pulse")} />
      {c.label}
    </span>
  );
}