import { TriangleAlert } from "lucide-react";

export default function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800">
      <div className="flex items-start gap-3">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}