"""
The chat pipeline with the model stubbed out: a scripted planner stands in for Groq, and the
narration falls back to its plain summary because no API key is configured in tests.
"""

import io
import json

import pandas as pd
import pytest

from app.models.dataset import Dataset
from app.schemas.semantic import (
    ColumnSchema,
    FilterSchema,
    MetricSchema,
    SemanticLayerSchema,
    TableSchema,
)
from app.services import chat_orchestrator as co
from app.services.llm_client import LLMResult
from app.services.storage import get_storage
from app.services.verified_store import example

FILTERED_SQL = (
    "SELECT region, SUM(amount) AS revenue FROM orders WHERE status <> 'test' "
    "GROUP BY 1 ORDER BY 2 DESC"
)
UNFILTERED_SQL = "SELECT region, SUM(amount) AS revenue FROM orders GROUP BY 1 ORDER BY 2 DESC"

LAYER = SemanticLayerSchema(
    dataset_id="chat-test",
    summary="Orders of a small shop.",
    tables=[
        TableSchema(
            name="orders",
            description="One row per order.",
            columns=[
                ColumnSchema(name="order_id", dtype="int64", role="identifier"),
                ColumnSchema(name="region", dtype="string", role="dimension"),
                ColumnSchema(name="amount", dtype="float64", role="measure"),
                ColumnSchema(name="status", dtype="string", role="dimension"),
            ],
        )
    ],
    metrics=[
        MetricSchema(
            id="m_rev", name="Revenue", table="orders", expression="SUM(amount)", description="Order value"
        )
    ],
    filters=[
        FilterSchema(
            id="f_test", table="orders", expression="status <> 'test'", description="Exclude test orders"
        )
    ],
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    df = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "region": ["North", "South", "North", "East"],
            "amount": [100.0, 50.0, 75.0, 20.0],
            "status": ["ok", "ok", "test", "ok"],
        }
    )
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    key = "parquet/chat-test/orders.parquet"
    get_storage().put_bytes(key, buffer.getvalue())
    columns = [
        {"name": name, "dtype": dtype, "distinct": 4, "nullPct": 0.0, "samples": []}
        for name, dtype in [
            ("order_id", "int64"), ("region", "string"), ("amount", "float64"), ("status", "string"),
        ]
    ]
    return Dataset(
        id="chat-test",
        name="orders",
        file_name="orders.csv",
        raw_key="raw/chat-test",
        profile={"tables": [{"table": "orders", "rows": 4, "parquetKey": key, "columns": columns}]},
    )


def plan(sql: str, **extra) -> dict:
    return {
        "answerable": True,
        "sql": sql,
        "chart": {"type": "bar", "x": "region", "y": ["revenue"]},
        "assumptions": "",
        **extra,
    }


class FakePlanner:
    """Stands in for the model: hands out scripted replies and keeps what it was asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, messages):
        self.prompts.append(messages[-1]["content"])
        reply = self.replies.pop(0)
        text = json.dumps(reply)
        return reply, LLMResult(text=text, model="fake", prompt_tokens=0, completion_tokens=0)


def ask(monkeypatch, dataset, replies, question="Revenue by region", history=(), verified=()):
    planner = FakePlanner(replies)
    monkeypatch.setattr(co, "_plan", planner)
    answer = co.answer_question(
        dataset=dataset, layer=LAYER, history=list(history), question=question, verified=list(verified)
    )
    return answer, planner


def test_a_default_filter_left_out_is_sent_back_once(monkeypatch, dataset):
    answer, planner = ask(monkeypatch, dataset, [plan(UNFILTERED_SQL), plan(FILTERED_SQL)])
    assert answer.success and answer.attempts == 2
    assert "default filter" in planner.prompts[1] and "status <> 'test'" in planner.prompts[1]
    assert answer.trust == "governed"
    assert answer.grounding["metricsUsed"] == [{"name": "Revenue", "expression": "SUM(amount)"}]
    assert [f["id"] for f in answer.grounding["filtersApplied"]] == ["f_test"]
    assert answer.row_count == 3  # the test order is gone
    assert answer.grounding["rowsPreview"][0] == {"region": "North", "revenue": 100.0}
    assert answer.chart["type"] == "bar"


def test_a_filter_still_missing_after_the_retry_is_flagged_not_hidden(monkeypatch, dataset):
    answer, planner = ask(monkeypatch, dataset, [plan(UNFILTERED_SQL), plan(UNFILTERED_SQL)])
    assert answer.attempts == 2 and len(planner.prompts) == 2
    assert answer.trust == "ad_hoc"
    assert [f["id"] for f in answer.grounding["filtersMissing"]] == ["f_test"]
    assert answer.grounding["reason"] == "Default filter not applied: Exclude test orders."
    assert 'rule "Exclude test orders" was not applied' in answer.content
    assert answer.grounding["rowsPreview"][0]["revenue"] == 175.0


def test_the_user_may_ask_for_the_excluded_rows(monkeypatch, dataset):
    skipped = [{"id": "f_test", "reason": "the user asked for all orders including test ones"}]
    answer, planner = ask(
        monkeypatch,
        dataset,
        [plan(UNFILTERED_SQL, skipped_filters=skipped)],
        question="Revenue by region including test orders",
    )
    assert answer.attempts == 1 and len(planner.prompts) == 1
    assert answer.trust == "ad_hoc"
    assert answer.grounding["filtersSkipped"][0]["reason"] == skipped[0]["reason"]
    assert answer.grounding["filtersMissing"] == []
    assert "was not applied" not in answer.content


def test_a_formula_outside_the_governed_metrics_is_ad_hoc(monkeypatch, dataset):
    sql = "SELECT region, AVG(amount) AS avg_amount FROM orders WHERE status <> 'test' GROUP BY 1"
    answer, _ = ask(monkeypatch, dataset, [plan(sql)], question="Average amount by region")
    assert answer.trust == "ad_hoc"
    assert answer.grounding["unmatchedAggregates"] == ["AVG(amount)"]
    assert answer.grounding["metricsUsed"] == []


def test_a_verified_question_is_answered_from_the_library(monkeypatch, dataset):
    known = example("Revenue by region", FILTERED_SQL)
    answer, planner = ask(monkeypatch, dataset, [], question="revenue by region?", verified=[known])
    assert planner.prompts == []  # the model was never asked
    assert answer.trust == "verified" and answer.attempts == 0 and answer.model is None
    assert answer.grounding["verifiedQuestion"] == "Revenue by region"
    assert answer.sql.lstrip().startswith("SELECT") and answer.row_count == 3


def test_with_earlier_turns_the_model_is_asked_and_shown_the_example(monkeypatch, dataset):
    known = example("Revenue by region", FILTERED_SQL)
    history = [
        {"role": "user", "content": "hi", "sql": None},
        {"role": "assistant", "content": "Hello.", "sql": None},
    ]
    answer, planner = ask(
        monkeypatch, dataset, [plan(FILTERED_SQL)], question="revenue by region", history=history, verified=[known]
    )
    assert answer.attempts == 1
    assert "VERIFIED EXAMPLES" in planner.prompts[0] and FILTERED_SQL in planner.prompts[0]
    assert answer.trust == "verified"  # the same calculation as the confirmed one


def test_verified_sql_that_predates_a_default_filter_is_not_reused(monkeypatch, dataset):
    known = example("Revenue by region", UNFILTERED_SQL)
    answer, planner = ask(monkeypatch, dataset, [plan(FILTERED_SQL)], verified=[known])
    assert len(planner.prompts) == 1 and answer.attempts == 1
    assert answer.trust == "governed"


def test_the_prompt_carries_the_governed_definitions(monkeypatch, dataset):
    _, planner = ask(monkeypatch, dataset, [plan(FILTERED_SQL)])
    prompt = planner.prompts[0]
    assert "GOVERNED METRICS" in prompt and "Revenue = SUM(amount)" in prompt
    assert "DEFAULT FILTERS" in prompt and "id=f_test table orders: status <> 'test'" in prompt
