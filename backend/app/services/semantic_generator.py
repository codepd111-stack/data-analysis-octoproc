import logging
import uuid

from app.core.config import settings
from app.schemas.semantic import (
    ColumnSchema,
    RelationshipSchema,
    SemanticLayerSchema,
    TableSchema,
)
from app.services.llm_client import LLMError, get_llm
from app.services.prompts import SEMANTIC_ENRICH_SYSTEM

logger = logging.getLogger(__name__)

VALID_ROLES = {"identifier", "dimension", "measure", "date"}
VALID_REL_TYPES = {"many-to-one", "one-to-many", "one-to-one"}
KEY_SUFFIXES = ("_id", "_key", "_code")

# Columns whose name contains one of these words never have sample values stored or sent
SENSITIVE_TOKENS = {
    "email", "phone", "mobile", "password", "passwd", "ssn", "aadhaar", "aadhar",
    "passport", "address", "dob", "birth", "iban", "card", "salary", "wage", "pan",
}


# ---------- helpers ----------


def _is_sensitive(name: str) -> bool:
    return bool(set(name.lower().split("_")) & SENSITIVE_TOKENS)


def _visible_samples(col: dict) -> list[str]:
    if not settings.include_sample_values or _is_sensitive(col["name"]):
        return []
    return list(col.get("samples", []))[:5]


def _guess_role(col: dict, rows: int) -> str:
    name, dtype = col["name"], col["dtype"]
    if dtype == "datetime":
        return "date"
    if name == "id" or name.endswith(KEY_SUFFIXES):
        return "identifier"
    if dtype == "string" and rows and col["distinct"] / rows > 0.9:
        return "identifier"
    if dtype in ("int64", "float64"):
        return "measure"
    return "dimension"


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _clean_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _new_rel_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------- relationship inference from the profile (no AI) ----------


def _is_unique_key(col: dict, rows: int) -> bool:
    return rows >= 2 and col["nullPct"] == 0 and col["distinct"] == rows


def _joinable(a: dict, b: dict) -> bool:
    if a["name"] == "id" or a["dtype"] != b["dtype"]:
        return False
    if a["dtype"] == "string":
        return True
    # Plain integers only count as keys when the name says so (avoids matching e.g. "units")
    return a["dtype"] == "int64" and a["name"].endswith(KEY_SUFFIXES)


def infer_relationships(tables: list[dict]) -> list[RelationshipSchema]:
    found: list[RelationshipSchema] = []
    for i, a in enumerate(tables):
        for b in tables[i + 1 :]:
            b_cols = {c["name"]: c for c in b["columns"]}
            for col_a in a["columns"]:
                col_b = b_cols.get(col_a["name"])
                if col_b is None or not _joinable(col_a, col_b):
                    continue
                a_unique = _is_unique_key(col_a, a["rows"])
                b_unique = _is_unique_key(col_b, b["rows"])
                if a_unique and b_unique:
                    child, parent, kind = a, b, "one-to-one"
                elif b_unique:
                    child, parent, kind = a, b, "many-to-one"
                elif a_unique:
                    child, parent, kind = b, a, "many-to-one"
                else:
                    continue
                found.append(
                    RelationshipSchema(
                        id=_new_rel_id(),
                        from_=f"{child['table']}.{col_a['name']}",
                        to=f"{parent['table']}.{col_a['name']}",
                        type=kind,
                    )
                )
    return found


# ---------- baseline layer (no AI) ----------


def build_baseline_layer(
    dataset_id: str, dataset_name: str, tables: list[dict]
) -> SemanticLayerSchema:
    """Heuristic layer from profiling alone. The AI step refines it afterwards."""
    layer_tables: list[TableSchema] = []
    total_rows = 0
    for t in tables:
        rows = t["rows"]
        total_rows += rows
        columns = [
            ColumnSchema(
                name=c["name"],
                dtype=c["dtype"],
                role=_guess_role(c, rows),
                description=_humanize(c["name"]),
                null_pct=c["nullPct"],
                distinct=c["distinct"],
                samples=_visible_samples(c),
            )
            for c in t["columns"]
        ]
        layer_tables.append(
            TableSchema(name=t["table"], description=f"Data from {t['table']}.", columns=columns)
        )

    count = len(layer_tables)
    return SemanticLayerSchema(
        dataset_id=dataset_id,
        summary=f"{dataset_name}: {count} table{'s' if count != 1 else ''}, {total_rows:,} rows in total.",
        tables=layer_tables,
        relationships=infer_relationships(tables),
        generated_by="heuristic",
    )


# ---------- AI enrichment ----------


def _short(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)[:30]


def _column_line(col: dict) -> str:
    parts = [col["name"], col["dtype"], f"{col['distinct']} distinct", f"{col['nullPct']}% null"]
    if "min" in col and "max" in col:
        parts.append(f"range {_short(col['min'])} to {_short(col['max'])}")
    samples = _visible_samples(col)
    if samples:
        parts.append("samples: " + ", ".join(samples))
    return " | ".join(parts)


def build_enrich_prompt(tables: list[dict]) -> str:
    blocks = []
    for t in tables:
        shown = t["columns"][: settings.semantic_max_columns]
        lines = "\n".join(f"  {_column_line(c)}" for c in shown)
        hidden = len(t["columns"]) - len(shown)
        extra = f"\n  (+{hidden} more columns not shown)" if hidden > 0 else ""
        blocks.append(f"TABLE {t['table']} ({t['rows']:,} rows)\n{lines}{extra}")
    return "\n\n".join(blocks)


def merge_llm_output(layer: SemanticLayerSchema, data: object) -> SemanticLayerSchema:
    """Apply the model's answer, keeping only what is valid. Anything unusable falls back to the baseline."""
    if not isinstance(data, dict):
        return layer

    tables_in = {
        t.get("name"): t for t in data.get("tables", []) if isinstance(t, dict)
    }

    new_tables: list[TableSchema] = []
    for table in layer.tables:
        t_in = tables_in.get(table.name, {})
        cols_in = {
            c.get("name"): c for c in t_in.get("columns", []) if isinstance(c, dict)
        }
        new_cols: list[ColumnSchema] = []
        for col in table.columns:
            c_in = cols_in.get(col.name, {})
            role = c_in.get("role")
            new_cols.append(
                col.model_copy(
                    update={
                        "description": _clean_str(c_in.get("description")) or col.description,
                        "role": role if isinstance(role, str) and role in VALID_ROLES else col.role,
                    }
                )
            )
        new_tables.append(
            table.model_copy(
                update={
                    "description": _clean_str(t_in.get("description")) or table.description,
                    "columns": new_cols,
                }
            )
        )

    # Relationships: both ends must exist with the same type, and must not duplicate one we already have
    dtypes = {f"{t.name}.{c.name}": c.dtype for t in new_tables for c in t.columns}
    relationships = list(layer.relationships)
    seen = {frozenset((r.from_, r.to)) for r in relationships}
    for r in data.get("relationships", []):
        if not isinstance(r, dict):
            continue
        src, dst, kind = r.get("from"), r.get("to"), r.get("type")
        if not (isinstance(src, str) and isinstance(dst, str) and isinstance(kind, str)):
            continue
        if src not in dtypes or dst not in dtypes or kind not in VALID_REL_TYPES:
            continue
        if src.split(".")[0] == dst.split(".")[0] or dtypes[src] != dtypes[dst]:
            continue
        pair = frozenset((src, dst))
        if pair in seen:
            continue
        seen.add(pair)
        relationships.append(
            RelationshipSchema(id=_new_rel_id(), from_=src, to=dst, type=kind)
        )

    return layer.model_copy(
        update={
            "summary": _clean_str(data.get("summary")) or layer.summary,
            "tables": new_tables,
            "relationships": relationships,
            "generated_by": "llm",
        }
    )


def enrich_layer(layer: SemanticLayerSchema, tables: list[dict]) -> SemanticLayerSchema:
    """Ask the model to describe the data. Never raises: on any failure the baseline is returned."""
    user_prompt = build_enrich_prompt(tables)
    try:
        data, result = get_llm().chat_json(
            [
                {"role": "system", "content": SEMANTIC_ENRICH_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4000,
        )
    except LLMError as exc:
        logger.warning("AI enrichment skipped: %s", exc)
        return layer

    logger.info(
        "AI enrichment done (%s prompt tokens, %s completion tokens)",
        result.prompt_tokens,
        result.completion_tokens,
    )
    return merge_llm_output(layer, data)