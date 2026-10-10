export type DatasetStatus = "processing" | "needs_review" | "approved" | "failed";

export interface Dataset {
  id: string;
  name: string;
  fileName: string;
  rows: number;
  columns: number;
  tableCount?: number;
  sizeLabel: string;
  status: DatasetStatus;
  uploadedAt: string; // ISO timestamp from the API
  progress?: number | null;
  stage?: string | null;
  error?: string | null;
}

export type ColumnRole = "identifier" | "dimension" | "measure" | "date";

export interface ColumnSemantic {
  name: string;
  dtype: string;
  role: ColumnRole;
  description: string;
  nullPct: number;
  distinct: number;
  samples: string[];
}

export interface TableSemantic {
  name: string;
  description: string;
  columns: ColumnSemantic[];
}

export interface Relationship {
  id: string;
  from: string;
  to: string;
  type: "many-to-one" | "one-to-many" | "one-to-one";
}

/** A governed measure: one aggregate over one table, agreed once and reused in every answer. */
export interface Metric {
  id: string;
  name: string;
  table: string;
  expression: string; // DuckDB aggregate, e.g. SUM(amount)
  description: string;
}

/** A default filter: the rows to keep unless the user asks otherwise, e.g. status <> 'test'. */
export interface DefaultFilter {
  id: string;
  table: string;
  expression: string;
  description: string;
}

export interface BusinessRule {
  id: string;
  text: string;
}

export interface SemanticLayer {
  datasetId: string;
  summary: string;
  tables: TableSemantic[];
  relationships: Relationship[];
  metrics: Metric[];
  filters: DefaultFilter[];
  rules: BusinessRule[];
  generatedBy?: "heuristic" | "llm";
}

export interface DefinitionCheck {
  id: string;
  kind: "metric" | "filter";
  ok: boolean;
  value?: string | null;
  problem?: string | null;
}

export interface QualityIssue {
  severity: "warning" | "info";
  table: string;
  column?: string | null;
  message: string;
}

export interface ChartSpec {
  type: "bar" | "line" | "pie";
  title: string;
  xKey: string;
  yKeys: string[];
  data: Record<string, string | number>[];
}

/**
 * verified = a person confirmed this exact calculation before; governed = built only from
 * approved metrics with every default filter applied; ad_hoc = the AI's own calculation.
 */
export type Trust = "verified" | "governed" | "ad_hoc";

export interface MetricUse {
  name: string;
  expression: string;
}

export interface FilterUse {
  id: string;
  table: string;
  expression: string;
  description: string;
  reason?: string | null; // for a skipped filter: why the user wanted those rows included
}

/** The receipts behind an answer. */
export interface Grounding {
  reason: string;
  metricsUsed: MetricUse[];
  filtersApplied: FilterUse[];
  filtersSkipped: FilterUse[];
  filtersMissing: FilterUse[];
  unmatchedAggregates: string[];
  tables: string[];
  columns: string[];
  rowsPreview: Record<string, string | number | boolean | null>[];
  rowCount: number;
  verifiedQuestion?: string | null;
}

export type Feedback = "up" | "down" | null;
export type FeedbackReason =
  | "wrong_numbers"
  | "wrong_chart"
  | "misunderstood"
  | "too_vague"
  | "other";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chart?: ChartSpec | null;
  sql?: string | null;
  feedback?: Feedback;
  feedbackReason?: FeedbackReason | null;
  trust?: Trust | null;
  grounding?: Grounding | null;
  createdAt: string;
}

export interface VerifiedQuery {
  id: string;
  datasetId: string;
  question: string;
  sql: string;
  standalone: boolean; // asked without earlier turns, so it can be reused on its own
  conversationId?: string | null;
  createdAt: string;
}

export interface Conversation {
  id: string;
  title: string;
  datasetId: string;
  datasetName: string;
  updatedAt: string; // ISO timestamp from the API
  messageCount: number;
  preview: string;
}

export interface ConversationPage {
  items: Conversation[];
  total: number;
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: ChatMessage[];
}

export type LogStatus = "ok" | "retried" | "failed" | "unanswerable" | "rate_limited";

export interface LogEntry {
  id: string;
  createdAt: string;
  question: string;
  status: LogStatus;
  attempts: number;
  latencyMs?: number | null;
  rowCount?: number | null;
  model?: string | null;
  sql?: string | null;
  error?: string | null;
  feedback?: string | null;
  feedbackReason?: string | null;
  trust?: Trust | null;
  datasetId?: string | null;
  datasetName?: string | null;
  conversationId?: string | null;
}

export interface LogPage {
  items: LogEntry[];
  total: number;
}

export interface ErrorCount {
  error: string;
  count: number;
}

export interface InsightsSummary {
  days?: number | null;
  total: number;
  answered: number;
  failed: number;
  unanswerable: number;
  retried: number;
  rateLimited: number;
  avgLatencyMs?: number | null;
  thumbsUp: number;
  thumbsDown: number;
  verified: number;
  governed: number;
  adHoc: number;
  topErrors: ErrorCount[];
}
