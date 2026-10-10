import pandas as pd
import pytest

from app.schemas.semantic import (
    ColumnSchema,
    FilterSchema,
    MetricSchema,
    RuleSchema,
    SemanticLayerSchema,
    TableSchema,
)
from app.services.definitions import (
    DefinitionError,
    check_definitions,
    definition_problems,
    validate_filter,
    validate_metric,
)
from app.services.semantic_generator import build_baseline_layer, merge_llm_output

COLUMNS = {"order_id", "customer_id", "amount", "status", "order_date"}


def layer_with(metrics=(), filters=(), rules=()) -> SemanticLayerSchema:
    table = TableSchema(
        name="orders",
        columns=[ColumnSchema(name=n, dtype="string", role="dimension") for n in sorted(COLUMNS)],
    )
    return SemanticLayerSchema(
        dataset_id="ds", tables=[table], metrics=list(metrics), filters=list(filters), rules=list(rules)
    )


# ---------- single expressions ----------


@pytest.mark.parametrize(
    "expression",
    [
        "SUM(amount)",
        "sum(Amount)",
        "COUNT(*)",
        "SUM(amount) AS total",
        "SUM(orders.amount)",
        "100.0 * SUM(amount) / COUNT(DISTINCT order_id)",
        "AVG(CASE WHEN status = 'paid' THEN amount END)",
    ],
)
def test_valid_metric_expressions(expression):
    validate_metric(expression, "orders", COLUMNS)


@pytest.mark.parametrize(
    "expression, message",
    [
        ("amount", "must aggregate"),
        ("SUM(amt)", "does not exist"),
        ("SUM(customers.amount)", "another table"),
        ("SUM(amount) OVER ()", "indow"),
        ("(SELECT SUM(amount) FROM orders)", "ub-queries"),
        ("SUM(amount), COUNT(*)", "exactly one"),
        ("", "empty"),
        ("SUM(", "could not read"),
        ("SUM(amount); DROP TABLE orders", "single expression"),
        ("*", "not an expression"),
    ],
)
def test_invalid_metric_expressions(expression, message):
    with pytest.raises(DefinitionError, match=message):
        validate_metric(expression, "orders", COLUMNS)


def test_filter_expressions():
    validate_filter("status <> 'test'", "orders", COLUMNS)
    validate_filter("orders.status != 'test' AND amount > 0", "orders", COLUMNS)
    with pytest.raises(DefinitionError, match="cannot aggregate"):
        validate_filter("SUM(amount) > 0", "orders", COLUMNS)
    with pytest.raises(DefinitionError, match="at least one column"):
        validate_filter("1 = 1", "orders", COLUMNS)
    with pytest.raises(DefinitionError, match="does not exist"):
        validate_filter("deleted = false", "orders", COLUMNS)


# ---------- a whole layer ----------


def test_definition_problems_name_each_bad_definition():
    layer = layer_with(
        metrics=[
            MetricSchema(id="m1", name="Revenue", table="orders", expression="SUM(amount)"),
            MetricSchema(id="m2", name="revenue", table="orders", expression="SUM(amount)"),
            MetricSchema(id="m3", name="Ghost", table="ghosts", expression="SUM(amount)"),
            MetricSchema(id="m4", name="Plain", table="orders", expression="amount"),
        ],
        filters=[FilterSchema(id="f1", table="orders", expression="COUNT(*) > 1", description="Busy")],
        rules=[RuleSchema(id="r1", text="  ")],
    )
    problems = definition_problems(layer)
    assert problems == [
        "Metric 'revenue': another metric has the same name.",
        "Metric 'Ghost': table 'ghosts' does not exist.",
        "Metric 'Plain': a metric must aggregate (SUM, COUNT, AVG, MIN, MAX, ...).",
        "Filter on orders ('Busy'): a filter cannot aggregate; it is a row-level condition such as status <> 'test'.",
        "A business rule is empty.",
    ]
    assert definition_problems(layer_with(metrics=[layer.metrics[0]])) == []


def col(name, dtype="string", distinct=3, null_pct=0.0, samples=None, **extra) -> dict:
    return {"name": name, "dtype": dtype, "distinct": distinct, "nullPct": null_pct, "samples": samples or [], **extra}


ORDERS = {
    "table": "orders",
    "rows": 3,
    "duplicateRows": 0,
    "columns": [
        col("order_id", "int64", 3),
        col("amount", "float64", 3, min=1.0, max=3.0),
        col("status", "string", 2, samples=["ok", "test"]),
    ],
}


def test_merge_keeps_only_usable_suggestions():
    layer = build_baseline_layer("ds", "Shop", [ORDERS])
    data = {
        "metrics": [
            {"name": "Revenue", "table": "orders", "expression": "SUM(amount)", "description": " Order value "},
            {"name": "revenue", "table": "orders", "expression": "SUM(amount)"},  # duplicate name
            {"name": "Orders", "table": "orders", "expression": "COUNT(DISTINCT order_id)"},
            {"name": "Ghost", "table": "orders", "expression": "SUM(nope)"},  # unknown column
            {"name": "Elsewhere", "table": "customers", "expression": "COUNT(*)"},  # unknown table
            {"name": "", "table": "orders", "expression": "COUNT(*)"},  # no name
            "garbage",
        ],
        "filters": [
            {"table": "orders", "expression": "status <> 'test'", "description": "Exclude test orders"},
            {"table": "orders", "expression": "SUM(amount) > 0"},
            {"table": "orders", "expression": ""},
        ],
        "rules": ["Amounts are in EUR.", "", "amounts are in EUR.", {"text": "One row per order line."}, 7],
    }
    merged = merge_llm_output(layer, data)

    assert [(m.name, m.expression, m.description) for m in merged.metrics] == [
        ("Revenue", "SUM(amount)", "Order value"),
        ("Orders", "COUNT(DISTINCT order_id)", ""),
    ]
    assert len({m.id for m in merged.metrics}) == 2 and all(m.id for m in merged.metrics)
    assert [(f.expression, f.description) for f in merged.filters] == [
        ("status <> 'test'", "Exclude test orders")
    ]
    assert [r.text for r in merged.rules] == ["Amounts are in EUR.", "One row per order line."]
    assert definition_problems(merged) == []


def test_layers_saved_before_definitions_existed_still_load():
    old = {"datasetId": "ds", "summary": "", "tables": [], "relationships": []}
    layer = SemanticLayerSchema.model_validate(old)
    assert (layer.metrics, layer.filters, layer.rules) == ([], [], [])


# ---------- against the data ----------


def test_check_definitions_runs_them_against_the_data(tmp_path):
    df = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "amount": [100.0, 50.0, 75.0, 20.0],
            "status": ["ok", "ok", "test", "ok"],
        }
    )
    path = tmp_path / "orders.parquet"
    df.to_parquet(path, index=False)
    layer = layer_with(
        metrics=[
            MetricSchema(id="m1", name="Revenue", table="orders", expression="SUM(amount)"),
            MetricSchema(id="m2", name="Orders", table="orders", expression="COUNT(*)"),
            MetricSchema(id="m3", name="Broken", table="orders", expression="SUM(amount) / nothing"),
        ],
        filters=[
            FilterSchema(id="f1", table="orders", expression="status <> 'test'"),
            FilterSchema(id="f2", table="orders", expression="status <> 'test' AND"),
        ],
    )

    results = {c.id: c for c in check_definitions(layer, {"orders": path})}
    assert results["f1"].ok and results["f1"].value == "keeps 3 of 4 rows"
    assert not results["f2"].ok and results["f2"].problem
    assert results["m1"].ok and results["m1"].value == "170"  # the working filter is applied
    assert results["m2"].ok and results["m2"].value == "3"
    assert not results["m3"].ok and "nothing" in results["m3"].problem

    # Without the data, the problem is reported rather than raised
    [only] = check_definitions(layer_with(metrics=[layer.metrics[0]]), {})
    assert not only.ok and "not available" in only.problem
