import json
from pathlib import Path

from app.services.chart_builder import build_chart
from app.services.query_engine import QueryError, run_query, validate_select

root = Path("data/uploads/parquet")
tables = None
for folder in sorted(root.iterdir()):
    found = {p.stem: p for p in folder.glob("*.parquet")}
    if {"orders", "customers"} <= found.keys():
        tables = found
if tables is None:
    raise SystemExit("Upload orders.csv + customers.csv with 'Combine' ticked first.")
allowed = set(tables)


def run(sql, hint=None):
    v = validate_select(sql, allowed)
    r = run_query({t: tables[t] for t in v.tables}, v.sql)
    print("SQL  :", v.sql.replace("\n", " "))
    print("ROWS :", r.rows[:4], f"({r.row_count} total)")
    print("CHART:", json.dumps(build_chart(r, hint))[:300])
    print()


run(
    "SELECT region, SUM(amount) AS total_amount FROM orders GROUP BY region ORDER BY total_amount DESC",
    {"type": "bar", "x": "region", "y": ["total_amount"]},
)
run(
    "SELECT strftime(order_date, '%Y-%m') AS month, SUM(amount) AS total_amount FROM orders GROUP BY 1 ORDER BY 1",
    {"type": "line", "x": "month", "y": ["total_amount"]},
)
run(
    "SELECT c.segment, o.region, SUM(o.amount) AS total_amount "
    "FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY 1, 2",
    {"x": "segment", "y": ["total_amount"]},
)

for bad in [
    "DROP TABLE orders",
    "SELECT * FROM read_parquet('data/uploads/x.parquet')",
    "SELECT * FROM secrets",
    "SELECT 1; SELECT 2",
]:
    try:
        v = validate_select(bad, allowed)
        run_query({t: tables[t] for t in v.tables}, v.sql)
        print("NOT BLOCKED:", bad)
    except QueryError as e:
        print("blocked:", bad, "->", str(e)[:90])