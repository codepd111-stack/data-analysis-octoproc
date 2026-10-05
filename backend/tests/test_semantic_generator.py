from app.services.semantic_generator import (
    _guess_role,
    _is_sensitive,
    build_baseline_layer,
    build_enrich_prompt,
    infer_relationships,
    merge_llm_output,
)


def col(name, dtype="string", distinct=3, null_pct=0.0, samples=None, **extra) -> dict:
    return {
        "name": name,
        "dtype": dtype,
        "distinct": distinct,
        "nullPct": null_pct,
        "samples": samples or [],
        **extra,
    }


ORDERS = {
    "table": "orders",
    "rows": 3,
    "duplicateRows": 0,
    "columns": [
        col("order_id", "int64", 3),
        col("customer_id", "int64", 2),
        col("amount", "float64", 3, min=1.0, max=3.0),
        col("order_date", "datetime", 3),
        col("email", samples=["a@x.com"]),
    ],
}
CUSTOMERS = {
    "table": "customers",
    "rows": 2,
    "duplicateRows": 0,
    "columns": [col("customer_id", "int64", 2), col("segment", "string", 2, samples=["SMB", "Ent"])],
}


def test_sensitive_column_names_are_detected_by_token():
    assert _is_sensitive("customer_email")
    assert _is_sensitive("DOB")
    assert not _is_sensitive("emailed_count")


def test_role_guessing():
    assert _guess_role(col("order_date", "datetime"), 10) == "date"
    assert _guess_role(col("customer_id", "int64"), 10) == "identifier"
    assert _guess_role(col("amount", "float64"), 10) == "measure"
    assert _guess_role(col("segment", "string", distinct=2), 10) == "dimension"
    assert _guess_role(col("sku", "string", distinct=10), 10) == "identifier"


def test_baseline_layer_hides_sensitive_samples():
    layer = build_baseline_layer("ds", "Shop", [ORDERS, CUSTOMERS])
    orders = {c.name: c for c in layer.tables[0].columns}
    customers = {c.name: c for c in layer.tables[1].columns}
    assert orders["email"].samples == []
    assert customers["segment"].samples == ["SMB", "Ent"]
    assert layer.generated_by == "heuristic"
    assert "2 tables" in layer.summary


def test_sensitive_samples_never_reach_the_prompt():
    prompt = build_enrich_prompt([ORDERS, CUSTOMERS])
    assert "a@x.com" not in prompt
    assert "SMB" in prompt


def test_relationships_are_inferred_from_shared_key_columns():
    [rel] = infer_relationships([ORDERS, CUSTOMERS])
    assert (rel.from_, rel.to, rel.type) == (
        "orders.customer_id",
        "customers.customer_id",
        "many-to-one",
    )


def test_merge_keeps_only_valid_model_output():
    layer = build_baseline_layer("ds", "Shop", [ORDERS, CUSTOMERS])
    data = {
        "summary": "  Orders and their customers. ",
        "tables": [
            {
                "name": "orders",
                "description": "Each row is an order.",
                "columns": [
                    {"name": "amount", "role": "measure", "description": "Order value"},
                    {"name": "customer_id", "role": "not-a-role", "description": ""},
                    {"name": "ghost", "role": "measure", "description": "does not exist"},
                ],
            },
            {"name": "unknown_table", "description": "ignored"},
        ],
        "relationships": [
            # duplicate of the inferred one
            {"from": "orders.customer_id", "to": "customers.customer_id", "type": "many-to-one"},
            # valid and new
            {"from": "orders.order_id", "to": "customers.customer_id", "type": "one-to-one"},
            # dtype mismatch
            {"from": "orders.amount", "to": "customers.segment", "type": "many-to-one"},
            # same table on both ends
            {"from": "orders.order_id", "to": "orders.customer_id", "type": "one-to-one"},
            # unknown relationship type
            {"from": "orders.order_id", "to": "customers.customer_id", "type": "sideways"},
            "garbage",
        ],
    }
    merged = merge_llm_output(layer, data)

    assert merged.summary == "Orders and their customers."
    assert merged.generated_by == "llm"
    orders = merged.tables[0]
    assert orders.description == "Each row is an order."
    cols = {c.name: c for c in orders.columns}
    assert cols["amount"].description == "Order value"
    assert cols["customer_id"].role == "identifier"  # invalid role: baseline kept
    assert cols["customer_id"].description == "Customer id"  # empty text: baseline kept
    assert "ghost" not in cols
    assert merged.tables[1].description == layer.tables[1].description
    assert [(r.from_, r.to) for r in merged.relationships] == [
        ("orders.customer_id", "customers.customer_id"),
        ("orders.order_id", "customers.customer_id"),
    ]


def test_merge_ignores_non_dict_output():
    layer = build_baseline_layer("ds", "Shop", [ORDERS])
    assert merge_llm_output(layer, "not json") is layer
