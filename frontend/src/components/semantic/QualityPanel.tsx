"use client";

import { useEffect, useState } from "react";
import { ChevronDown, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import type { QualityIssue } from "@/lib/types";

export default function QualityPanel({ datasetId }: { datasetId: string }) {
  const [issues, setIssues] = useState<QualityIssue[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getQuality(datasetId)
      .then((list) => {
        if (!cancelled) setIssues(list);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  // This panel is optional help, so it stays quiet if the request fails
  if (failed || issues === null) return null;

  if (issues.length === 0) {
    return (
      <div className="mb-6 flex items-center gap-3 rounded-2xl border border-octo-green/30 bg-octo-green-soft px-5 py-4 text-sm text-octo-green-dark">
        <CircleCheck className="h-4 w-4 shrink-0" />
        No data-quality problems found in the profile.
      </div>
    );
  }

  const warnings = issues.filter((i) => i.severity === "warning").length;

  return (
    <details
      open={warnings > 0}
      className="group mb-6 rounded-2xl border border-amber-200 bg-amber-50/60"
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4 text-sm font-medium text-amber-900">
        <TriangleAlert className="h-4 w-4 shrink-0" />
        Data quality: {warnings} warning{warnings === 1 ? "" : "s"}
        {issues.length - warnings > 0 ? `, ${issues.length - warnings} note${issues.length - warnings === 1 ? "" : "s"}` : ""}
        <ChevronDown className="ml-auto h-4 w-4 transition-transform group-open:rotate-180" />
      </summary>
      <ul className="space-y-2 border-t border-amber-200 px-5 py-4">
        {issues.map((issue, i) => (
          <li key={i} className="flex items-start gap-3 text-sm text-slate-700">
            {issue.severity === "warning" ? (
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
            )}
            <span>
              <span className="font-mono text-xs text-slate-900">
                {issue.table}
                {issue.column ? `.${issue.column}` : ""}
              </span>{" "}
              {issue.message}
            </span>
          </li>
        ))}
      </ul>
      <p className="border-t border-amber-200 px-5 py-3 text-xs text-slate-500">
        These checks run on the profile from when the file was uploaded. Clean the source file and
        re-upload it if a warning matters for your questions.
      </p>
    </details>
  );
}