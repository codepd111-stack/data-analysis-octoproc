import sqlglot

from app.schemas.semantic import (
    ColumnSchema,
    FilterSchema,
    MetricSchema,
    SemanticLayerSchema,
    TableSchema,
)
from app.services.grounding import assess, canonical, find_usage, missing_filters
from app.services.query_engine import QueryResult


def table(name, *columns) -> TableSchema:
    return TableSchema(
        name=name, columns=[ColumnSchema(name=c, dtype="string", role="dimension") for c in columns]
    )


LAYER = SemanticLayerSchema(
    dataset_id="ds",
    tables=[
        table("orders", "order_id", "customer_id", "amount", "status", "region"),
        table("customers", "customer_id", "segment"),
    ],
    metrics=[
        MetricSchema(id="m_rev", name="Revenue", table="orders", expression="SUM(amount)"),
        MetricSchema(
            id="m_aov",
            name="Average order value",
            table="orders",
            expression="SUM(amount) / COUNT(DISTINCT order_id)",
        ),
    ],
    filters=[
        FilterSchema(
            id="f_test", table="orders", expression="status <> 'test'", description="Exclude test orders"
        )
    ],
)
RESULT = QueryResult(
    columns=["segment", "revenue"], rows=[{"segment": "SMB", "revenue": 1.5}], row_count=1, truncated=False
)
BOTH = {"orders", "customers"}


def test_canonical_ignores_table_prefixes_case_and_formatting():
    a = sqlglot.parse_one("SELECT sum( O.Amount )", read="duckdb").expressions[0]
    b = sqlglot.parse_one("SELECT SUM(amount)", read="duckdb").expressions[0]
    assert canonical(a) == canonical(b) == "SUM(amount)"


def test_metric_and_filter_are_recognised_however_the_model_wrote_them():
    sql = (
        "SELECT c.segment, round(sum(O.Amount), 2) AS revenue FROM orders o "
        "JOIN customers c ON o.customer_id = c.customer_id WHERE o.status != 'test' GROUP BY 1"
    )
    usage = find_usage(sql, LAYER, BOTH)
    assert [m.name for m in usage.metrics] == ["Revenue"]
    assert usage.unmatched_aggregates == []
    assert [f.id for f in usage.applied] == ["f_test"]
    assert usage.missing == []


def test_a_compound_metric_counts_once():
    sql = (
        "SELECT region, SUM(amount) / COUNT(DISTINCT order_id) AS aov FROM orders "
        "WHERE status <> 'test' GROUP BY 1"
    )
    usage = find_usage(sql, LAYER, {"orders"})
    assert [m.name for m in usage.metrics] == ["Average order value"]
    assert usage.unmatched_aggregates == []


def test_aggregates_outside_governed_metrics_are_reported():
    sql = (
        "SELECT SUM(amount) AS revenue, AVG(amount) AS avg_amount, COUNT(*) AS n "
        "FROM orders WHERE status <> 'test'"
    )
    usage = find_usage(sql, LAYER, {"orders"})
    assert [m.name for m in usage.metrics] == ["Revenue"]
    assert usage.unmatched_aggregates == ["AVG(amount)", "COUNT(*)"]


def test_filters_count_inside_ctes_and_only_for_tables_read():
    cte = "WITH clean AS (SELECT * FROM orders WHERE status <> 'test') SELECT COUNT(*) AS n FROM clean"
    assert [f.id for f in find_usage(cte, LAYER, {"orders"}).applied] == ["f_test"]
    customers_only = "SELECT segment, COUNT(*) AS n FROM customers GROUP BY 1"
    assert find_usage(customers_only, LAYER, {"customers"}).missing == []


def test_missing_filters_honour_what_the_user_asked_to_skip():
    sql = "SELECT SUM(amount) AS revenue FROM orders"
    assert [f.id for f in missing_filters(sql, LAYER, {"orders"}, set())] == ["f_test"]
    assert missing_filters(sql, LAYER, {"orders"}, {"f_test"}) == []


def grade(sql, tables=frozenset({"orders"}), skipped=None, verified=None):
    return assess(
        sql=sql,
        layer=LAYER,
        tables_read=set(tables),
        result=RESULT,
        skipped=skipped or {},
        verified_question=verified,
    )


def test_trust_badges():
    governed_sql = "SELECT SUM(amount) AS revenue FROM orders WHERE status <> 'test'"
    trust, g = grade(governed_sql)
    assert trust == "governed"
    assert g.reason == "Built only from governed metrics (Revenue), with every default filter applied."

    trust, g = grade("SELECT SUM(amount) AS revenue FROM orders")
    assert trust == "ad_hoc" and g.reason == "Default filter not applied: Exclude test orders."
    assert [f.id for f in g.filters_missing] == ["f_test"]

    trust, g = grade(
        "SELECT SUM(amount) AS revenue FROM orders", skipped={"f_test": "user wants test orders too"}
    )
    assert trust == "ad_hoc"
    assert g.filters_skipped[0].reason == "user wants test orders too" and g.filters_missing == []

    trust, g = grade("SELECT AVG(amount) AS a FROM orders WHERE status <> 'test'")
    assert trust == "ad_hoc"
    assert g.reason == "Uses calculations that are not governed metrics: AVG(amount)."

    trust, g = grade("SELECT order_id FROM orders WHERE status <> 'test'")
    assert trust == "ad_hoc" and g.reason.startswith("A direct look at the rows")

    trust, g = grade(governed_sql, verified="revenue after test orders")
    assert trust == "verified" and g.verified_question == "revenue after test orders"

    # A calculation verified before a default filter existed is not passed off as verified
    trust, g = grade("SELECT SUM(amount) AS revenue FROM orders", verified="revenue")
    assert trust == "ad_hoc" and g.verified_question is None


def test_grounding_carries_the_receipts():
    _, g = grade("SELECT SUM(amount) AS revenue FROM orders WHERE status <> 'test'", tables=BOTH)
    assert g.tables == ["customers", "orders"]
    assert g.columns == ["segment", "revenue"]
    assert g.rows_preview == RESULT.rows and g.row_count == 1
    assert g.metrics_used[0].expression == "SUM(amount)"
    assert g.filters_applied[0].description == "Exclude test orders"
