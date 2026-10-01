import json
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.core.config import settings

QUERY_TIMEOUT_SECONDS = 15


class QueryError(ValueError):
    """Invalid or failing SQL. The message is safe to feed back to the LLM for a retry."""


@dataclass
class ValidatedQuery:
    sql: str
    tables: set[str]  # real table names the query reads from


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool


def validate_select(
    sql: str, allowed_tables: set[str], max_rows: int | None = None
) -> ValidatedQuery:
    """Accept exactly one SELECT over known tables, enforce a LIMIT, return DuckDB-dialect SQL."""
    max_rows = max_rows or settings.max_query_rows
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except SqlglotError as exc:
        raise QueryError(f"SQL could not be parsed: {exc}") from exc

    if len(statements) != 1:
        raise QueryError("Exactly one SQL statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise QueryError("Only SELECT queries are allowed.")

    lookup = {t.lower(): t for t in allowed_tables}
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    used: set[str] = set()
    for table in tree.find_all(exp.Table):
        if not table.name:
            raise QueryError("Table functions (such as reading files) are not allowed.")
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in lookup:
            available = ", ".join(sorted(allowed_tables))
            raise QueryError(
                f"Table '{table.name}' is not available. Available tables: {available}."
            )
        used.add(lookup[name])

    if tree.args.get("limit") is None:
        tree = tree.limit(max_rows)
    return ValidatedQuery(sql=tree.sql(dialect="duckdb", pretty=True), tables=used)


def run_query(table_paths: dict[str, Path], sql: str) -> QueryResult:
    """
    Load the needed tables into an in-memory DuckDB, lock down file/network access,
    then run the (already validated) query with a time limit.
    """
    con = duckdb.connect(database=":memory:")
    timed_out = threading.Event()

    def _interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(QUERY_TIMEOUT_SECONDS, _interrupt)
    try:
        con.execute(f"SET memory_limit='{settings.duckdb_memory_limit}'")
        for name, path in table_paths.items():
            safe_path = path.as_posix().replace("'", "''")
            con.execute(f"CREATE TABLE \"{name}\" AS SELECT * FROM read_parquet('{safe_path}')")
        con.execute("SET enable_external_access=false")
        con.execute("SET lock_configuration=true")
        timer.start()
        df = con.execute(sql).fetchdf()
    except Exception as exc:  # noqa: BLE001
        if timed_out.is_set():
            raise QueryError(
                "The query took too long and was stopped. Make it simpler or add filters."
            ) from exc
        raise QueryError(str(exc)) from exc
    finally:
        timer.cancel()
        con.close()

    head = df.head(settings.max_query_rows).copy()

    # Duplicate column names (SELECT a, a) would break JSON export
    seen: dict[str, int] = {}
    names = []
    for col in map(str, head.columns):
        n = seen.get(col, 0)
        seen[col] = n + 1
        names.append(col if n == 0 else f"{col}_{n + 1}")
    head.columns = names

    # Readable dates: drop the time part when every value is at midnight
    for col in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[col]):
            valid = head[col].dropna()
            has_time = bool((valid != valid.dt.normalize()).any())
            head[col] = head[col].dt.strftime("%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d")

    return QueryResult(
        columns=list(head.columns),
        rows=json.loads(head.to_json(orient="records", date_format="iso")),
        row_count=len(df),
        truncated=len(df) > settings.max_query_rows,
    )