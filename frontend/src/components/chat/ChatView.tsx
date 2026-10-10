import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Database, Plus, Send, Sparkles } from "lucide-react";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Skeleton from "@/components/ui/Skeleton";
import { api, ApiError, errorMessage } from "@/lib/api";
import { buildSuggestions } from "@/lib/suggestions";
import type { ChatMessage, Dataset } from "@/lib/types";
import { formatDuration, uid } from "@/lib/utils";

type Phase = "loading" | "ready" | "error";

export default function ChatView({
  initialDatasetId,
  conversationId: initialConversationId,
}: {
  initialDatasetId?: string | null;
  conversationId?: string | null;
}) {
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(
    initialConversationId ?? null
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>(() => buildSuggestions(null));

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0); // > 0 while the AI service has us waiting
  const bottomRef = useRef<HTMLDivElement>(null);
  const coolingDown = secondsLeft > 0;

  // Initial load: approved datasets, plus the conversation if one was requested
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const all = await api.listDatasets();
        const approved = all.filter((d) => d.status === "approved");

        let selected = approved.find((d) => d.id === initialDatasetId)?.id ?? approved[0]?.id ?? "";
        let loaded: ChatMessage[] = [];
        if (initialConversationId) {
          const detail = await api.getConversation(initialConversationId);
          loaded = detail.messages;
          if (approved.some((d) => d.id === detail.conversation.datasetId)) {
            selected = detail.conversation.datasetId;
          }
        }

        if (cancelled) return;
        setDatasets(approved);
        setDatasetId(selected);
        setMessages(loaded);
        setConversationId(initialConversationId ?? null);
        setPhase("ready");
      } catch (e) {
        if (cancelled) return;
        setLoadError(errorMessage(e));
        setPhase("error");
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [initialDatasetId, initialConversationId, reloadKey]);

  // Starter questions come from the selected dataset's semantic layer
  useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;
    api
      .getSemantic(datasetId)
      .then((layer) => {
        if (!cancelled) setSuggestions(buildSuggestions(layer));
      })
      .catch(() => {
        if (!cancelled) setSuggestions(buildSuggestions(null));
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Countdown after the AI service rate-limits us
  useEffect(() => {
    if (!coolingDown) return;
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [coolingDown, secondsLeft]);

  function newChat(nextDatasetId: string) {
    setMessages([]);
    setConversationId(null);
    setSendError(null);
    setInput("");
    navigate(`/chat?dataset=${nextDatasetId}`, { replace: true });
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || sending || coolingDown || !datasetId) return;

    const optimistic: ChatMessage = {
      id: `tmp-${uid()}`,
      role: "user",
      content: question,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    setSending(true);
    setSendError(null);

    try {
      const res = await api.sendChat({ datasetId, conversationId, question });
      setConversationId(res.conversationId);
      setMessages((prev) => [...prev, res.message]);
    } catch (e) {
      // Take the message back out and restore the text so the user can simply resend
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setInput(question);
      if (e instanceof ApiError && e.status === 429) {
        setSecondsLeft(e.retryAfter ?? 30);
      } else {
        setSendError(errorMessage(e));
      }
    } finally {
      setSending(false);
    }
  }

  const blocked = sending || coolingDown;

  if (phase === "loading") {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14" />
        <Skeleton className="h-[28rem]" />
      </div>
    );
  }

  if (phase === "error") {
    return (
      <ErrorBanner
        message={loadError ?? "Could not load chat."}
        onRetry={() => {
          setPhase("loading");
          setReloadKey((k) => k + 1);
        }}
      />
    );
  }

  if (datasets.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center">
        <p className="text-sm text-slate-600">No dataset is approved yet.</p>
        <Link to="/review" className="mt-3 inline-block text-sm font-medium text-octo-green">
          Go to Semantic Review
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:h-[calc(100dvh-4rem)]">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-slate-400" />
          <select
            value={datasetId}
            onChange={(e) => {
              setDatasetId(e.target.value);
              newChat(e.target.value);
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => newChat(datasetId)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
        >
          <Plus className="h-4 w-4" /> New chat
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        {messages.length === 0 && !sending ? (
          <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-octo-green-soft text-octo-green">
              <Sparkles className="h-6 w-6" />
            </div>
            <h2 className="mt-4 text-lg font-semibold text-slate-900">Ask anything about your data</h2>
            <p className="mt-1 text-sm text-slate-500">
              Every answer comes with a written explanation, a chart, and the evidence behind it.
            </p>
            <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={blocked}
                  className="rounded-xl border border-slate-200 px-4 py-3 text-left text-sm text-slate-600 transition-colors hover:border-octo-green/50 hover:bg-octo-green-soft disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {sending && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-slate-200 bg-white px-4 py-4 sm:px-6">
        {coolingDown && (
          <div className="mx-auto mb-3 max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800">
            The AI service is busy (free-tier limit reached). You can send again in{" "}
            <strong>{formatDuration(secondsLeft)}</strong>. Your question is kept in the box.
          </div>
        )}
        {sendError && (
          <div className="mx-auto mb-3 max-w-3xl">
            <ErrorBanner message={sendError} />
          </div>
        )}
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            rows={1}
            placeholder="Ask a question about your data…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || blocked}
            aria-label="Send"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-octo-green text-white transition-colors hover:bg-octo-green-dark disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-400">
          Answers come from your approved semantic layer and query results. The model never sees your raw file.
        </p>
      </div>
    </div>
  );
}