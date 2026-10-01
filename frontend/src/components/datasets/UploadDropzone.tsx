"use client";

import { useRef, useState } from "react";
import { CloudUpload } from "lucide-react";
import { cn } from "@/lib/utils";

const ACCEPT = ".csv,.xlsx,.xls,.parquet";

export default function UploadDropzone({
  onFiles,
  busy = false,
}: {
  onFiles: (files: File[]) => void;
  busy?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handle(list: FileList | null) {
    if (busy || !list || list.length === 0) return;
    onFiles(Array.from(list));
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handle(e.dataTransfer.files);
      }}
      className={cn(
        "rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
        dragging
          ? "border-octo-green bg-octo-green-soft"
          : "border-slate-300 bg-white hover:border-slate-400",
        busy && "opacity-70"
      )}
    >
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-octo-green-soft text-octo-green">
        <CloudUpload className="h-6 w-6" />
      </div>
      <p className="mt-4 text-sm font-medium text-slate-900">
        {busy ? "Uploading…" : "Drag and drop your data files here"}
      </p>
      <p className="mt-1 text-sm text-slate-500">CSV, Excel or Parquet. Each file becomes a dataset.</p>
      <button
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="mt-5 rounded-lg bg-octo-green px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-octo-green-dark disabled:cursor-not-allowed disabled:opacity-60"
      >
        Browse files
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          handle(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}