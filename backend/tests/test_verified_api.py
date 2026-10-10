"""
Thumbs-up -> verified library -> the same question answered without the model, over the API.
Also the definition checks on the review endpoints. The AI is never involved: enrichment is
stubbed, the verified path needs no model, and narration falls back to a plain summary.
"""

from datetime import timedelta

import pytest

from app.core.utils import utcnow
from app.models.conversation import Conversation, Message, QueryLog
from app.services import ingestion

ORDERS_CSV = (
    b"Order ID,Customer ID,Region,Amount,Order Date\n"
    b"1,10,North,100,2024-01-05\n"
    b"2,10,South,50,2024-01-20\n"
    b"3,20,North,75,2024-02-02\n"
)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(ingestion, "enrich_layer", lambda layer, profiles: layer)


def approved_dataset(client) -> str:
    response = client.post(
        "/api/datasets/upload",
        files=[("files", ("orders.csv", ORDERS_CSV, "text/csv"))],
        data={"combine": "false"},
    )
    assert response.status_code == 201, response.text
    [created] = response.json()
    assert client.post(f"/api/datasets/{created['id']}/approve").status_code == 200
    return created["id"]


def answered_message(db, dataset_id: str, question: str, sql: str) -> Message:
    """What chat leaves behind after an answer: the question, the answer with its SQL, a log row."""
    now = utcnow()
    conversation = Conversation(dataset_id=dataset_id, title=question)
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content=question, created_at=now))
    assistant = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Answer.",
        sql=sql,
        trust="ad_hoc",
        created_at=now + timedelta(seconds=1),
    )
    db.add(assistant)
    db.flush()
    db.add(
        QueryLog(
            conversation_id=conversation.id,
            message_id=assistant.id,
            dataset_id=dataset_id,
            question=question,
            generated_sql=sql,
            attempts=1,
            success=True,
            row_count=2,
            trust="ad_hoc",
        )
    )
    db.commit()
    return assistant


def test_thumbs_up_builds_the_library_and_the_question_is_answered_from_it(client, db):
    dataset_id = approved_dataset(client)
    message = answered_message(
        db,
        dataset_id,
        "Total amount by region",
        "SELECT region, SUM(amount) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC",
    )

    assert client.post("/api/chat/feedback", json={"messageId": message.id, "feedback": "up"}).status_code == 204
    [entry] = client.get(f"/api/datasets/{dataset_id}/verified").json()
    assert entry["question"] == "Total amount by region" and entry["standalone"] is True
    assert entry["conversationId"] == message.conversation_id

    # The same question in a fresh chat: answered from the library, badge Verified, with receipts
    response = client.post("/api/chat", json={"datasetId": dataset_id, "question": "total amount by region?"})
    assert response.status_code == 200, response.text
    answer = response.json()["message"]
    assert answer["trust"] == "verified"
    assert answer["grounding"]["verifiedQuestion"] == "Total amount by region"
    assert answer["grounding"]["rowsPreview"] == [
        {"region": "North", "total": 175},
        {"region": "South", "total": 50},
    ]
    assert answer["grounding"]["tables"] == ["orders"]
    assert "175" in answer["content"]

    # The badge is kept in the log for the insights page
    logs = client.get("/api/insights/logs?filter=all").json()["items"]
    assert logs[0]["question"] == "total amount by region?" and logs[0]["trust"] == "verified"
    assert client.get("/api/insights/summary").json()["verified"] >= 1
    assert client.get("/api/insights/logs?filter=ad_hoc").status_code == 200

    # Taking the thumbs-up back removes the entry
    assert client.post("/api/chat/feedback", json={"messageId": message.id, "feedback": None}).status_code == 204
    assert client.get(f"/api/datasets/{dataset_id}/verified").json() == []


def test_a_thumbs_up_on_a_follow_up_is_kept_but_not_reused_on_its_own(client, db):
    dataset_id = approved_dataset(client)
    message = answered_message(
        db, dataset_id, "and by region?", "SELECT region, COUNT(*) AS orders FROM orders GROUP BY 1"
    )
    # An earlier exchange in the same conversation makes this answer depend on context
    earlier = utcnow() - timedelta(minutes=5)
    db.add_all(
        [
            Message(conversation_id=message.conversation_id, role="user", content="How many orders?", created_at=earlier),
            Message(
                conversation_id=message.conversation_id,
                role="assistant",
                content="3.",
                created_at=earlier + timedelta(seconds=1),
            ),
        ]
    )
    db.commit()

    client.post("/api/chat/feedback", json={"messageId": message.id, "feedback": "up"})
    [entry] = client.get(f"/api/datasets/{dataset_id}/verified").json()
    assert entry["standalone"] is False

    assert client.delete(f"/api/datasets/{dataset_id}/verified/{entry['id']}").status_code == 204
    assert client.get(f"/api/datasets/{dataset_id}/verified").json() == []
    assert client.delete(f"/api/datasets/{dataset_id}/verified/{entry['id']}").status_code == 404


def test_bad_definitions_are_refused_but_can_be_checked_first(client):
    dataset_id = approved_dataset(client)
    layer = client.get(f"/api/datasets/{dataset_id}/semantic").json()
    layer["metrics"] = [
        {"id": "m1", "name": "Revenue", "table": "orders", "expression": "SUM(amount)", "description": "Order value"},
        {"id": "m2", "name": "Broken", "table": "orders", "expression": "SUM(nope)", "description": ""},
    ]
    layer["filters"] = [
        {"id": "f1", "table": "orders", "expression": "region <> 'South'", "description": "Exclude South"}
    ]

    checks = {c["id"]: c for c in client.post(f"/api/datasets/{dataset_id}/semantic/check", json=layer).json()}
    assert checks["f1"]["ok"] and checks["f1"]["value"] == "keeps 2 of 3 rows"
    assert checks["m1"]["ok"] and checks["m1"]["value"] == "175"  # with the filter applied
    assert not checks["m2"]["ok"] and "nope" in checks["m2"]["problem"]

    refused = client.put(f"/api/datasets/{dataset_id}/semantic", json=layer)
    assert refused.status_code == 422 and "Broken" in refused.json()["detail"]

    del layer["metrics"][1]
    saved = client.put(f"/api/datasets/{dataset_id}/semantic", json=layer)
    assert saved.status_code == 200
    assert [m["name"] for m in saved.json()["metrics"]] == ["Revenue"]
    assert client.post(f"/api/datasets/{dataset_id}/approve").status_code == 200
