import { useState } from "react";
import { ChevronDown, Code, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import type { ChatMessage, Feedback, FeedbackReason } from "@/lib/types";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import ChartRenderer from "./ChartRenderer";

const REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "wrong_numbers", label: "Wrong numbers" },
  { value: "wrong_chart", label: "Wrong chart" },
  { value: "misunderstood", label: "Misunderstood my question" },
  { value: "too_vague", label: "Too vague" },
  { value: "other", label: "Other" },
];

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [feedback, setFeedback] = useState<Feedback>(message.feedback ?? null);
  const [reason, setReason] = useState<FeedbackReason | null>(message.feedbackReason ?? null);
  const [askReason, setAskReason] = useState(false);

  async function toggleFeedback(kind: "up" | "down") {
    const previous = { feedback, reason, askReason };
    const next = feedback === kind ? null : kind;
    setFeedback(next); // optimistic
    setReason(null);
    setAskReason(next === "down");
    try {
      await api.sendFeedback(message.id, next, null);
    } catch {
      setFeedback(previous.feedback); // roll back if the server rejected it
      setReason(previous.reason);
      setAskReason(previous.askReason);
    }
  }

  async function pickReason(value: FeedbackReason) {
    const previous = reason;
    setReason(value);
    setAskReason(false);
    try {
      await api.sendFeedback(message.id, "down", value);
    } catch {
      setReason(previous);
    }
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md bg-octo-green px-4 py-3 text-sm leading-relaxed text-white sm:max-w-[70%]">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-octo-green-soft text-octo-green">
        <Sparkles className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        <div className="whitespace-pre-line rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700 shadow-sm">
          {message.content}
        </div>

        {message.chart && <ChartRenderer spec={message.chart} />}

        {message.sql && (
          <details className="group rounded-xl border border-slate-200 bg-white">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-500 hover:text-slate-700">
              <Code className="h-3.5 w-3.5" />
              How this was calculated
              <ChevronDown className="ml-auto h-4 w-4 transition-transform group-open:rotate-180" />
            </summary>
            <pre className="overflow-x-auto border-t border-slate-100 bg-slate-50 px-4 py-3 font-mono text-xs leading-relaxed text-slate-700">
              {message.sql}
            </pre>
          </details>
        )}

        <div className="flex flex-wrap items-center gap-1">
          {(["up", "down"] as const).map((kind) => {
            const Icon = kind === "up" ? ThumbsUp : ThumbsDown;
            return (
              <button
                key={kind}
                onClick={() => toggleFeedback(kind)}
                aria-label={kind === "up" ? "Good answer" : "Bad answer"}
                className={cn(
                  "rounded-lg p-1.5 transition-colors",
                  feedback === kind
                    ? kind === "up"
                      ? "bg-octo-green-soft text-octo-green"
                      : "bg-rose-50 text-rose-600"
                    : "text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                )}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
          {feedback === "down" && reason && !askReason && (
            <span className="ml-1 text-xs text-slate-400">
              Noted: {REASONS.find((r) => r.value === reason)?.label ?? reason}
            </span>
          )}
        </div>

        {feedback === "down" && askReason && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">What went wrong?</span>
            {REASONS.map((r) => (
              <button
                key={r.value}
                onClick={() => pickReason(r.value)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition-colors hover:border-octo-green/50 hover:bg-octo-green-soft"
              >
                {r.label}
              </button>
            ))}
            <button
              onClick={() => setAskReason(false)}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              Skip
            </button>
          </div>
        )}
      </div>
    </div>
  );
}