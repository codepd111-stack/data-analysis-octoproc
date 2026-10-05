import pandas as pd
import pytest

from app.core.config import settings
from app.services.query_engine import QueryError, run_query, validate_select

ALLOWED = {"orders", "customers"}


@pytest.fixture(scope="module")
def tables(tmp_path_factory):
    folder = tmp_path_factory.mktemp("parquet")
    orders = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "customer_id": [10, 10, 20, 30],
            "region": ["North", "South", "North", "East"],
            "amount": [100.0, 50.5, 75.0, 20.0],
            "order_date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-02", "2024-02-15"]),
        }
    )
    customers = pd.DataFrame({"customer_id": [10, 20, 30], "segment": ["SMB", "Enterprise", "SMB"]})
    paths = {"orders": folder / "orders.parquet", "customers": folder / "customers.parquet"}
    orders.to_parquet(paths["orders"], index=False)
    customers.to_parquet(paths["customers"], index=False)
    return paths


# ---------- validate_select ----------


def test_adds_limit_and_reports_tables():
    v = validate_select(
        "SELECT region, SUM(amount) AS total FROM orders GROUP BY region", ALLOWED, max_rows=50
    )
    assert v.tables == {"orders"}
    assert "LIMIT 50" in v.sql


def test_keeps_an_existing_limit():
    v = validate_select("SELECT * FROM orders LIMIT 3", ALLOWED, max_rows=50)
    assert "LIMIT 3" in v.sql
    assert "LIMIT 50" not in v.sql


def test_table_names_are_case_insensitive():
    assert validate_select("SELECT * FROM Orders", ALLOWED).tables == {"orders"}


def test_ctes_are_allowed_and_not_mistaken_for_tables():
    sql = "WITH big AS (SELECT * FROM orders WHERE amount > 60) SELECT COUNT(*) FROM big"
    assert validate_select(sql, ALLOWED).tables == {"orders"}


def test_join_collects_every_table_read():
    sql = (
        "SELECT c.segment, SUM(o.amount) FROM orders o "
        "JOIN customers c ON o.customer_id = c.customer_id GROUP BY 1"
    )
    assert validate_select(sql, ALLOWED).tables == ALLOWED


@pytest.mark.parametrize(
    "sql, message",
    [
        ("DROP TABLE orders", "Only SELECT"),
        ("DELETE FROM orders", "Only SELECT"),
        ("UPDATE orders SET amount = 0", "Only SELECT"),
        ("SELECT * FROM read_parquet('secret.parquet')", "Table functions"),
        ("SELECT * FROM secrets", "not available"),
        ("SELECT 1; SELECT 2", "Exactly one"),
        ("SELECT * FROM orders WHERE", "could not be parsed"),
    ],
)
def test_rejects_unsafe_or_broken_sql(sql, message):
    with pytest.raises(QueryError, match=message):
        validate_select(sql, ALLOWED)


# ---------- run_query ----------


def test_runs_a_grouped_query(tables):
    v = validate_select(
        "SELECT region, SUM(amount) AS total FROM orders GROUP BY region ORDER BY total DESC",
        ALLOWED,
    )
    r = run_query({t: tables[t] for t in v.tables}, v.sql)
    assert r.columns == ["region", "total"]
    assert r.rows[0] == {"region": "North", "total": 175.0}
    assert r.row_count == 3
    assert not r.truncated


def test_join_across_tables(tables):
    v = validate_select(
        "SELECT c.segment, SUM(o.amount) AS total FROM orders o "
        "JOIN customers c ON o.customer_id = c.customer_id GROUP BY 1 ORDER BY 1",
        ALLOWED,
    )
    r = run_query({t: tables[t] for t in v.tables}, v.sql)
    assert r.rows == [{"segment": "Enterprise", "total": 75.0}, {"segment": "SMB", "total": 170.5}]


def test_dates_at_midnight_lose_the_time_part(tables):
    v = validate_select("SELECT order_date FROM orders ORDER BY order_date", ALLOWED)
    r = run_query({"orders": tables["orders"]}, v.sql)
    assert r.rows[0]["order_date"] == "2024-01-05"


def test_duplicate_column_names_are_made_unique(tables):
    v = validate_select("SELECT region, region FROM orders", ALLOWED)
    r = run_query({"orders": tables["orders"]}, v.sql)
    assert len(r.columns) == 2
    assert len(set(r.columns)) == 2


def test_rows_are_truncated_to_the_configured_maximum(tables, monkeypatch):
    monkeypatch.setattr(settings, "max_query_rows", 2)
    v = validate_select("SELECT * FROM orders", ALLOWED, max_rows=10)
    r = run_query({"orders": tables["orders"]}, v.sql)
    assert len(r.rows) == 2
    assert r.row_count == 4
    assert r.truncated


def test_file_access_is_blocked_inside_duckdb(tables):
    # validate_select already refuses this; the DuckDB lockdown is the second line of defence
    path = tables["customers"].as_posix()
    with pytest.raises(QueryError):
        run_query({"orders": tables["orders"]}, f"SELECT * FROM read_parquet('{path}')")


def test_sql_errors_become_query_errors(tables):
    with pytest.raises(QueryError, match="no_such_column"):
        run_query({"orders": tables["orders"]}, "SELECT no_such_column FROM orders")
