"""
How an answer is grounded: which governed metrics and default filters its SQL really uses, and
the trust badge that follows. Detection is structural (sqlglot), not a self-report by the model,
so a badge cannot be talked into existence.

  verified  a person confirmed this exact calculation before (see verified_store.py)
  governed  every aggregate is a governed metric and every default filter is applied
  ad_hoc    anything else: the model's own formula, or a default filter left out
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.schemas.chat import FilterUse, GroundingSchema, MetricUse
from app.schemas.semantic import FilterSchema, MetricSchema, SemanticLayerSchema
from app.services.query_engine import QueryResult

PREVIEW_ROWS = 10


def canonical(node: exp.Expression) -> str:
    """Comparable text for an expression: table prefixes dropped, identifiers lower-cased."""
    node = node.copy()
    for col in node.find_all(exp.Column):
        col.set("table", None)
    for ident in node.find_all(exp.Identifier):
        ident.set("this", ident.this.lower())
    return node.sql(dialect="duckdb")


def _parse_expr(text: str) -> exp.Expression | None:
    try:
        tree = sqlglot.parse_one(f"SELECT {text}", read="duckdb")
    except SqlglotError:
        return None
    if not isinstance(tree, exp.Select) or len(tree.expressions) != 1:
        return None
    node = tree.expressions[0]
    return node.this if isinstance(node, exp.Alias) else node


def _within(node: exp.Expression, ancestors: list[exp.Expression]) -> bool:
    current: exp.Expression | None = node
    while current is not None:
        if any(current is a for a in ancestors):
            return True
        current = current.parent
    return False


@dataclass
class Usage:
    metrics: list[MetricSchema]
    applied: list[FilterSchema]  # default filters found in a WHERE clause
    missing: list[FilterSchema]  # default filters for tables the query reads that are not applied
    unmatched_aggregates: list[str]  # aggregates that are not part of any governed metric


def find_usage(sql: str, layer: SemanticLayerSchema, tables_read: set[str]) -> Usage:
    required = [f for f in layer.filters if f.table in tables_read]
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except SqlglotError:
        return Usage([], [], required, [])

    # Metrics: any part of the query whose canonical form equals a metric's expression. Once a
    # node matches, its inner aggregates belong to it (SUM(x) inside SUM(x) / COUNT(*) is not a
    # second metric), so the walk does not descend into matched nodes.
    wanted: dict[str, MetricSchema] = {}
    for m in layer.metrics:
        node = _parse_expr(m.expression)
        if node is not None:
            wanted.setdefault(canonical(node), m)
    matched: list[exp.Expression] = []
    used: dict[str, MetricSchema] = {}
    for node in tree.walk(bfs=False, prune=lambda n: any(n is m for m in matched)):
        if not wanted or node.find(exp.AggFunc) is None:
            continue
        metric = wanted.get(canonical(node))
        if metric is not None:
            matched.append(node)
            used.setdefault(metric.id, metric)
    unmatched = [
        canonical(agg) for agg in tree.find_all(exp.AggFunc) if not _within(agg, matched)
    ]

    # Filters: applied when the condition appears, as written, inside any WHERE clause
    conditions: set[str] = set()
    for where in tree.find_all(exp.Where):
        conditions.update(canonical(n) for n in where.this.walk())
    applied: list[FilterSchema] = []
    missing: list[FilterSchema] = []
    for f in required:
        node = _parse_expr(f.expression)
        if node is not None and canonical(node) in conditions:
            applied.append(f)
        else:
            missing.append(f)

    return Usage(list(used.values()), applied, missing, list(dict.fromkeys(unmatched)))


def missing_filters(
    sql: str, layer: SemanticLayerSchema, tables_read: set[str], skipped_ids: set[str]
) -> list[FilterSchema]:
    """Default filters the query should apply but does not, ignoring ones the user asked to skip."""
    return [f for f in find_usage(sql, layer, tables_read).missing if f.id not in skipped_ids]


def _use(f: FilterSchema, reason: str | None = None) -> FilterUse:
    return FilterUse(
        id=f.id, table=f.table, expression=f.expression, description=f.description, reason=reason
    )


def _describe(filters: list[FilterSchema]) -> str:
    return "; ".join(f.description or f.expression for f in filters)


def assess(
    *,
    sql: str,
    layer: SemanticLayerSchema,
    tables_read: set[str],
    result: QueryResult,
    skipped: dict[str, str],
    verified_question: str | None,
) -> tuple[str, GroundingSchema]:
    """The trust badge for an answer and the receipts that justify it."""
    usage = find_usage(sql, layer, tables_read)
    filters_skipped = [f for f in usage.missing if f.id in skipped]
    filters_missing = [f for f in usage.missing if f.id not in skipped]
    names = ", ".join(m.name for m in usage.metrics)

    if verified_question is not None and not filters_missing:
        trust = "verified"
        reason = f'A person confirmed this exact calculation before, for "{verified_question}".'
    elif (
        usage.metrics
        and not usage.unmatched_aggregates
        and not filters_missing
        and not filters_skipped
    ):
        trust = "governed"
        reason = f"Built only from governed metrics ({names})"
        reason += ", with every default filter applied." if usage.applied else "."
    else:
        trust = "ad_hoc"
        if filters_missing:
            reason = f"Default filter not applied: {_describe(filters_missing)}."
        elif filters_skipped:
            reason = f"Left out a default filter at the user's request: {_describe(filters_skipped)}."
        elif usage.unmatched_aggregates:
            shown = ", ".join(usage.unmatched_aggregates[:4])
            reason = (
                f"Combines governed metrics ({names}) with calculations that are not governed: {shown}."
                if usage.metrics
                else f"Uses calculations that are not governed metrics: {shown}."
            )
        elif not layer.metrics:
            reason = "No governed metrics are defined for this dataset yet, so this is the model's own calculation."
        else:
            reason = "A direct look at the rows; no governed metric was involved."

    grounding = GroundingSchema(
        reason=reason,
        metrics_used=[MetricUse(name=m.name, expression=m.expression) for m in usage.metrics],
        filters_applied=[_use(f) for f in usage.applied],
        filters_skipped=[_use(f, skipped[f.id]) for f in filters_skipped],
        filters_missing=[_use(f) for f in filters_missing],
        unmatched_aggregates=usage.unmatched_aggregates,
        tables=sorted(tables_read),
        columns=result.columns,
        rows_preview=result.rows[:PREVIEW_ROWS],
        row_count=result.row_count,
        verified_question=verified_question if trust == "verified" else None,
    )
    return trust, grounding
