"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

const STAGES = [
  "Understanding your question…",
  "Writing the query…",
  "Running it on your data…",
  "Writing the explanation…",
];

export default function TypingIndicator() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 3500);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-octo-green-soft text-octo-green">
        <Sparkles className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-3 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex gap-1">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
        <span className="text-xs text-slate-500">{STAGES[stage]}</span>
      </div>
    </div>
  );
}