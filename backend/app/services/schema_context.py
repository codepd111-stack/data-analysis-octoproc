from app.core.config import settings
from app.models.dataset import Dataset
from app.schemas.semantic import ColumnSchema, SemanticLayerSchema
from app.services.dataset_tables import get_table_profiles
from app.services.semantic_generator import _is_sensitive


def _fmt(value: object) -> str:
    if isinstance(value, str):
        return value[:10]  # ISO dates -> YYYY-MM-DD
    if isinstance(value, (int, float)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)[:12]


def _extra(col: ColumnSchema, prof: dict | None) -> str:
    parts: list[str] = []

    if prof and "min" in prof and "max" in prof and (
        col.role == "date" or col.dtype in ("int64", "float64")
    ):
        parts.append(f"range {_fmt(prof['min'])} to {_fmt(prof['max'])}")

    show_samples = (
        settings.include_sample_values
        and not _is_sensitive(col.name)
        and col.samples
        and col.role in ("dimension", "identifier")
    )
    if col.role == "dimension":
        parts.append(f"{col.distinct} distinct")
    if show_samples:
        prefix = "values: " if col.distinct <= len(col.samples) else "e.g. "
        parts.append(prefix + ", ".join(col.samples[:5]))

    if col.null_pct >= 5:
        parts.append(f"{col.null_pct:g}% null")
    return "; ".join(parts)


def build_schema_prompt(
    dataset: Dataset, layer: SemanticLayerSchema, allowed: set[str]
) -> str:
    profiles = get_table_profiles(dataset)
    by_table = {p["table"]: {c["name"]: c for c in p["columns"]} for p in profiles}
    row_counts = {p["table"]: p["rows"] for p in profiles}

    blocks: list[str] = []
    for table in layer.tables:
        if table.name not in allowed:
            continue
        prof_cols = by_table.get(table.name, {})
        lines = []
        for col in table.columns[: settings.semantic_max_columns]:
            desc = (col.description or "").replace("\n", " ").strip()[:120]
            parts = [col.name, col.dtype, col.role]
            if desc:
                parts.append(desc)
            extra = _extra(col, prof_cols.get(col.name))
            if extra:
                parts.append(extra)
            lines.append("  " + " | ".join(parts))

        header = f"TABLE {table.name} ({row_counts.get(table.name, 0):,} rows)"
        if table.description:
            header += f" - {table.description.strip()[:160]}"
        blocks.append(header + "\n" + "\n".join(lines))

    rels = [
        f"  {r.from_} -> {r.to} ({r.type})"
        for r in layer.relationships
        if r.from_.split(".")[0] in allowed and r.to.split(".")[0] in allowed
    ]

    out = ["DATASET: " + (layer.summary or "").strip(), ""]
    out.append("Columns are listed as: name | type | role | meaning | extra info")
    out.append("")
    out.append("\n\n".join(blocks))
    if rels:
        out += ["", "RELATIONSHIPS (join on these columns)", *rels]

    # Governed definitions, approved by a person. The pipeline checks afterwards that the SQL
    # really used them (services/grounding.py), so the wording here asks for exact copies.
    metrics = [m for m in layer.metrics if m.table in allowed]
    if metrics:
        out += ["", "GOVERNED METRICS (copy the expression exactly when the question asks for the metric)"]
        for m in metrics:
            line = f"  {m.name} = {m.expression}  [table {m.table}]"
            if m.description.strip():
                line += f" - {m.description.strip()[:120]}"
            out.append(line)

    filters = [f for f in layer.filters if f.table in allowed]
    if filters:
        out += [
            "",
            "DEFAULT FILTERS (put the expression in the WHERE clause whenever the table is read; "
            "skipped_filters is the only exception)",
        ]
        for f in filters:
            line = f"  id={f.id} table {f.table}: {f.expression}"
            if f.description.strip():
                line += f" - {f.description.strip()[:120]}"
            out.append(line)

    rules = [r.text.strip()[:300] for r in layer.rules if r.text.strip()]
    if rules:
        out += ["", "BUSINESS RULES", *[f"  - {text}" for text in rules]]
    return "\n".join(out)