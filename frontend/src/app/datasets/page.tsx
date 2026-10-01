"use client";

import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import UploadDropzone from "@/components/datasets/UploadDropzone";
import DatasetCard from "@/components/datasets/DatasetCard";
import { api, errorMessage } from "@/lib/api";
import type { Dataset } from "@/lib/types";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [combine, setCombine] = useState(false);

  const load = useCallback(async () => {
    try {
      setDatasets(await api.listDatasets());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is still processing
  const hasProcessing = datasets?.some((d) => d.status === "processing") ?? false;
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [hasProcessing, load]);

  async function handleFiles(files: File[]) {
    setUploading(true);
    setUploadError(null);
    try {
      const created = await api.uploadDatasets(files, combine && files.length > 1);
      setDatasets((prev) => [...created, ...(prev ?? [])]);
    } catch (e) {
      setUploadError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleRetry(id: string) {
    try {
      const updated = await api.retryDataset(id);
      setDatasets((prev) => (prev ? prev.map((d) => (d.id === id ? updated : d)) : prev));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const list = datasets ?? [];
  const stats = [
    { label: "Total datasets", value: list.length },
    { label: "Awaiting review", value: list.filter((d) => d.status === "needs_review").length },
    { label: "Ready for chat", value: list.filter((d) => d.status === "approved").length },
  ];

  return (
    <>
      <PageHeader
        title="Datasets"
        description="Upload company data, watch it get profiled, and track which datasets are ready to analyse."
      />

      <UploadDropzone onFiles={handleFiles} busy={uploading} />

      <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
        <input
          type="checkbox"
          checked={combine}
          onChange={(e) => setCombine(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-octo-green"
        />
        <span>
          <span className="font-medium text-slate-800">Combine multiple files into one dataset.</span>{" "}
          Tick this before uploading when the files belong together (for example orders and customers),
          so the agent can relate them. Excel files with several sheets are combined automatically.
        </span>
      </label>

      {uploadError && (
        <div className="mt-4">
          <ErrorBanner message={uploadError} />
        </div>
      )}

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.label} className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <p className="text-2xl font-semibold text-slate-900">{datasets ? s.value : "–"}</p>
            <p className="text-sm text-slate-500">{s.label}</p>
          </div>
        ))}
      </div>

      <h2 className="mb-4 mt-10 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Your datasets
      </h2>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {!error && datasets === null && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      )}

      {datasets && datasets.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
          No datasets yet. Upload a file above to get started.
        </p>
      )}

      {datasets && datasets.length > 0 && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {datasets.map((d) => (
            <DatasetCard key={d.id} dataset={d} onRetry={handleRetry} />
          ))}
        </div>
      )}
    </>
  );
}