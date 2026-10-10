import type { ColumnSemantic, SemanticLayer } from "./types";

const GENERIC = [
  "Give me an overview of this dataset",
  "How many rows are there?",
  "Which columns have the most missing values?",
  "What are the main categories in this data?",
];

const label = (c: ColumnSemantic) => c.name.replace(/_/g, " ");

export function buildSuggestions(layer: SemanticLayer | null): string[] {
  const table = layer?.tables[0];
  if (!table) return GENERIC;

  const measures = table.columns.filter((c) => c.role === "measure");
  const dims = table.columns.filter((c) => c.role === "dimension");
  const dates = table.columns.filter((c) => c.role === "date");
  const metrics = (layer?.metrics ?? []).filter((m) => m.table === table.name);

  const out: string[] = [];
  // Governed metrics first: questions phrased with them come back as governed answers
  if (metrics[0] && dims[0]) out.push(`${metrics[0].name} by ${label(dims[0])}`);
  if (metrics[1] && dates[0]) out.push(`${metrics[1].name} by month`);
  if (measures[0] && dims[0]) out.push(`Total ${label(measures[0])} by ${label(dims[0])}`);
  if (measures[0] && dates[0]) out.push(`Show ${label(measures[0])} by month`);
  if (dims[0]) out.push(`What share does each ${label(dims[0])} account for?`);
  if (measures[1] && dims[0]) out.push(`Average ${label(measures[1])} by ${label(dims[0])}`);
  else if (dims[1]) out.push(`Count of rows by ${label(dims[1])}`);

  return [...out, ...GENERIC].slice(0, 4);
}