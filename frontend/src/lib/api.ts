import { clearToken, getToken } from "./auth";
import type {
  ChatResponse,
  ConversationDetail,
  ConversationPage,
  Dataset,
  Feedback,
  FeedbackReason,
  InsightsSummary,
  LogPage,
  QualityIssue,
  SemanticLayer,
} from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  retryAfter?: number; // seconds, set when the server says "try again later"
  constructor(message: string, status: number, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

function goToLogin() {
  clearToken();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    // Not inside a component, so no router here. A full navigation is wanted anyway:
    // it drops every piece of in-memory state from the expired session.
    window.location.assign(new URL("/login", window.location.origin).href);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  opts: { auth?: boolean } = {}
): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0);
  }

  // A 401 means the sign-in expired or is missing (login and health calls opt out of this)
  if (res.status === 401 && opts.auth !== false) {
    goToLogin();
    throw new ApiError("Please sign in.", 401);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let retryAfter: number | undefined;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        const msgs = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean);
        if (msgs.length) detail = msgs.join("; ");
      }
      if (typeof body.retryAfter === "number") retryAfter = body.retryAfter;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, res.status, retryAfter);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  // Server and sign-in
  health: () => request<{ status: string }>("/api/health", undefined, { auth: false }),
  authStatus: () =>
    request<{ authRequired: boolean }>("/api/auth/status", undefined, { auth: false }),
  login: (code: string) =>
    request<{ token: string; expiresAt: number }>(
      "/api/auth/login",
      jsonInit("POST", { code }),
      { auth: false }
    ),

  // Datasets
  listDatasets: () => request<Dataset[]>("/api/datasets"),
  getDataset: (id: string) => request<Dataset>(`/api/datasets/${id}`),
  uploadDatasets: (files: File[], combine = false) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("combine", String(combine));
    // No Content-Type header: the browser sets the multipart boundary itself
    return request<Dataset[]>("/api/datasets/upload", { method: "POST", body: form });
  },
  retryDataset: (id: string) =>
    request<Dataset>(`/api/datasets/${id}/retry`, { method: "POST" }),

  // Semantic layer
  getSemantic: (id: string) => request<SemanticLayer>(`/api/datasets/${id}/semantic`),
  saveSemantic: (id: string, layer: SemanticLayer) =>
    request<SemanticLayer>(`/api/datasets/${id}/semantic`, jsonInit("PUT", layer)),
  approveDataset: (id: string) =>
    request<Dataset>(`/api/datasets/${id}/approve`, { method: "POST" }),
  regenerateSemantic: (id: string) =>
    request<SemanticLayer>(`/api/datasets/${id}/semantic/regenerate`, { method: "POST" }),
  getQuality: (id: string) => request<QualityIssue[]>(`/api/datasets/${id}/quality`),

  // Chat
  sendChat: (body: { datasetId: string; conversationId?: string | null; question: string }) =>
    request<ChatResponse>("/api/chat", jsonInit("POST", body)),
  sendFeedback: (messageId: string, feedback: Feedback, reason?: FeedbackReason | null) =>
    request<void>(
      "/api/chat/feedback",
      jsonInit("POST", { messageId, feedback, reason: reason ?? null })
    ),

  // History
  listConversations: (p: { q?: string; limit?: number; offset?: number } = {}) =>
    request<ConversationPage>(`/api/history${qs(p)}`),
  getConversation: (id: string) => request<ConversationDetail>(`/api/history/${id}`),
  deleteConversation: (id: string) =>
    request<void>(`/api/history/${id}`, { method: "DELETE" }),

  // Insights
  getInsights: (days?: number) => request<InsightsSummary>(`/api/insights/summary${qs({ days })}`),
  listLogs: (p: { filter?: string; days?: number; limit?: number; offset?: number }) =>
    request<LogPage>(`/api/insights/logs${qs(p)}`),
  // A plain link can't carry the sign-in header, so the CSV is fetched and saved as a blob
  exportLogs: async (filter = "all", days?: number): Promise<Blob> => {
    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    let res: Response;
    try {
      res = await fetch(`${BASE}/api/insights/export${qs({ filter, days })}`, {
        headers,
        cache: "no-store",
      });
    } catch {
      throw new ApiError("Can't reach the server. Is the backend running?", 0);
    }
    if (res.status === 401) {
      goToLogin();
      throw new ApiError("Please sign in.", 401);
    }
    if (!res.ok) throw new ApiError(`Export failed (${res.status})`, res.status);
    return res.blob();
  },
};