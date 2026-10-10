"""
Governed definitions: the metrics, default filters and business rules a person approves in the
semantic layer. This module makes sure an expression is safe and refers to real columns, and can
try every definition against the data so the reviewer sees a real number before approving.
"""

from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.schemas.semantic import DefinitionCheck, SemanticLayerSchema
from app.services.query_engine import QueryError, run_query, validate_select

MAX_EXPRESSION_CHARS = 500


class DefinitionError(ValueError):
    """An expression that cannot be used, explained for the person editing the layer."""


def parse_expression(text: str) -> exp.Expression:
    """One scalar DuckDB expression: no extra statements, no aliases, no sub-queries."""
    text = (text or "").strip().rstrip(";").strip()
    if not text:
        raise DefinitionError("the expression is empty.")
    if len(text) > MAX_EXPRESSION_CHARS:
        raise DefinitionError(f"the expression is longer than {MAX_EXPRESSION_CHARS} characters.")
    try:
        statements = [s for s in sqlglot.parse(f"SELECT {text}", read="duckdb") if s is not None]
    except SqlglotError as exc:
        first_line = str(exc).splitlines()[0][:160]
        raise DefinitionError(f"could not read the expression ({first_line}).") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise DefinitionError("write a single expression, not a statement.")
    projections = statements[0].expressions
    if len(projections) != 1:
        raise DefinitionError("write exactly one expression (no top-level commas).")
    node = projections[0]
    if isinstance(node, exp.Alias):
        node = node.this  # "SUM(x) AS total": the alias is harmless but not needed
    if isinstance(node, exp.Star):
        raise DefinitionError("'*' on its own is not an expression.")
    if node.find(exp.Select, exp.Subquery):
        raise DefinitionError("sub-queries are not allowed in a definition.")
    return node


def _check_columns(node: exp.Expression, table: str, columns: set[str]) -> None:
    for col in node.find_all(exp.Column):
        if col.table and col.table.lower() != table.lower():
            raise DefinitionError(
                f"'{col.sql()}' refers to another table; use only columns of {table}."
            )
        if col.name.lower() not in columns:
            raise DefinitionError(f"column '{col.name}' does not exist in table {table}.")


def validate_metric(expression: str, table: str, columns: set[str]) -> exp.Expression:
    node = parse_expression(expression)
    if node.find(exp.Window):
        raise DefinitionError("window functions (OVER) are not allowed; a metric is a plain aggregate.")
    if not node.find(exp.AggFunc):
        raise DefinitionError("a metric must aggregate (SUM, COUNT, AVG, MIN, MAX, ...).")
    _check_columns(node, table, columns)
    return node


def validate_filter(expression: str, table: str, columns: set[str]) -> exp.Expression:
    node = parse_expression(expression)
    if node.find(exp.AggFunc, exp.Window):
        raise DefinitionError(
            "a filter cannot aggregate; it is a row-level condition such as status <> 'test'."
        )
    if not node.find(exp.Column):
        raise DefinitionError("a filter must mention at least one column.")
    _check_columns(node, table, columns)
    return node


def table_columns(layer: SemanticLayerSchema) -> dict[str, set[str]]:
    return {t.name: {c.name.lower() for c in t.columns} for t in layer.tables}


def definition_problems(layer: SemanticLayerSchema) -> list[str]:
    """Everything wrong with the layer's definitions, worded for the reviewer. Empty when all is well."""
    columns = table_columns(layer)
    problems: list[str] = []

    names: set[str] = set()
    for m in layer.metrics:
        label = f"Metric '{m.name.strip() or m.id}'"
        key = m.name.strip().lower()
        if not key:
            problems.append(f"{label}: needs a name.")
        elif key in names:
            problems.append(f"{label}: another metric has the same name.")
        names.add(key)
        if m.table not in columns:
            problems.append(f"{label}: table '{m.table}' does not exist.")
            continue
        try:
            validate_metric(m.expression, m.table, columns[m.table])
        except DefinitionError as exc:
            problems.append(f"{label}: {exc}")

    for f in layer.filters:
        label = f"Filter on {f.table}"
        if f.description.strip():
            label += f" ('{f.description.strip()}')"
        if f.table not in columns:
            problems.append(f"{label}: table '{f.table}' does not exist.")
            continue
        try:
            validate_filter(f.expression, f.table, columns[f.table])
        except DefinitionError as exc:
            problems.append(f"{label}: {exc}")

    if any(not r.text.strip() for r in layer.rules):
        problems.append("A business rule is empty.")
    return problems


# ---------- trying definitions against the data ----------


def _format(value: object) -> str:
    if value is None:
        return "no value (NULL)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        # DuckDB hands back SUM over integers as a float; whole numbers read better without ".00"
        return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"
    return str(value)[:80]


def _first_row(table: str, path: Path, sql: str) -> dict:
    validated = validate_select(sql, {table})
    return run_query({table: path}, validated.sql).rows[0]


def check_definitions(
    layer: SemanticLayerSchema, table_paths: dict[str, Path]
) -> list[DefinitionCheck]:
    """
    Runs each filter (how many rows does it keep?) and then each metric, with the table's working
    filters applied, so the number shown is the one chat would use.
    """
    columns = table_columns(layer)
    results: list[DefinitionCheck] = []
    working: dict[str, list[str]] = {}  # table -> filter expressions that ran without error

    def _path(table: str) -> Path:
        if table not in columns:
            raise DefinitionError(f"table '{table}' does not exist.")
        path = table_paths.get(table)
        if path is None:
            raise DefinitionError("the data for this table is not available; upload it again.")
        return path

    for f in layer.filters:
        check = DefinitionCheck(id=f.id, kind="filter", ok=False)
        try:
            path = _path(f.table)
            validate_filter(f.expression, f.table, columns[f.table])
            row = _first_row(
                f.table,
                path,
                f"SELECT COUNT(*) AS total, "
                f"SUM(CASE WHEN {f.expression} THEN 1 ELSE 0 END) AS kept FROM {f.table}",
            )
            kept, total = int(row["kept"] or 0), int(row["total"] or 0)
            check.ok, check.value = True, f"keeps {kept:,} of {total:,} rows"
            working.setdefault(f.table, []).append(f.expression)
        except (DefinitionError, QueryError) as exc:
            check.problem = str(exc)
        results.append(check)

    for m in layer.metrics:
        check = DefinitionCheck(id=m.id, kind="metric", ok=False)
        try:
            path = _path(m.table)
            validate_metric(m.expression, m.table, columns[m.table])
            sql = f"SELECT {m.expression} AS value FROM {m.table}"
            if working.get(m.table):
                sql += " WHERE " + " AND ".join(f"({e})" for e in working[m.table])
            check.ok, check.value = True, _format(_first_row(m.table, path, sql)["value"])
        except (DefinitionError, QueryError) as exc:
            check.problem = str(exc)
        results.append(check)

    return results
