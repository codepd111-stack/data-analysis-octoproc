"""
Upload -> pipeline -> review, end to end against local storage and SQLite.
FastAPI's TestClient runs background tasks before returning, so the pipeline has finished by
the time the upload response is back. The AI enrichment step is stubbed: it needs a Groq key
and the pipeline is designed to work without it.
"""

import pytest

from app.services import ingestion

ORDERS_CSV = (
    b"Order ID,Customer ID,Region,Amount,Order Date\n"
    b"1,10,North,100,2024-01-05\n"
    b"2,10,South,50,2024-01-20\n"
    b"3,20,North,75,2024-02-02\n"
)
CUSTOMERS_CSV = b"Customer ID,Segment\n10,SMB\n20,Enterprise\n"


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(ingestion, "enrich_layer", lambda layer, profiles: layer)


def upload(client, files, combine=False):
    response = client.post(
        "/api/datasets/upload",
        files=[("files", (name, data, "text/csv")) for name, data in files],
        data={"combine": "true" if combine else "false"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_unknown_file_types_are_refused(client):
    response = client.post(
        "/api/datasets/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))]
    )
    assert response.status_code == 400


def test_upload_runs_the_pipeline_through_to_review(client):
    [created] = upload(client, [("orders.csv", ORDERS_CSV)])
    assert created["status"] == "processing"  # the response is sent before the job runs

    ds = client.get(f"/api/datasets/{created['id']}").json()
    assert ds["status"] == "needs_review", ds.get("error")
    assert (ds["rows"], ds["columns"], ds["tableCount"]) == (3, 5, 1)
    assert ds["name"] == "orders"

    layer = client.get(f"/api/datasets/{created['id']}/semantic").json()
    [table] = layer["tables"]
    assert table["name"] == "orders"
    columns = {c["name"]: c for c in table["columns"]}
    assert set(columns) == {"order_id", "customer_id", "region", "amount", "order_date"}
    assert columns["order_date"]["role"] == "date"
    assert columns["amount"]["role"] == "measure"
    assert layer["generatedBy"] == "heuristic"

    assert client.get(f"/api/datasets/{created['id']}/quality").status_code == 200
    assert client.get("/api/datasets/does-not-exist").status_code == 404


def test_combined_upload_becomes_one_dataset_with_a_relationship(client):
    [created] = upload(
        client, [("orders.csv", ORDERS_CSV), ("customers.csv", CUSTOMERS_CSV)], combine=True
    )
    ds = client.get(f"/api/datasets/{created['id']}").json()
    assert ds["status"] == "needs_review", ds.get("error")
    assert ds["tableCount"] == 2
    assert ds["name"] == "orders + customers"

    layer = client.get(f"/api/datasets/{created['id']}/semantic").json()
    # Files are processed in storage-key order, so tables come out alphabetically
    assert [t["name"] for t in layer["tables"]] == ["customers", "orders"]
    [rel] = layer["relationships"]
    assert (rel["from"], rel["to"], rel["type"]) == (
        "orders.customer_id",
        "customers.customer_id",
        "many-to-one",
    )


def test_separate_uploads_become_separate_datasets(client):
    created = upload(client, [("orders.csv", ORDERS_CSV), ("customers.csv", CUSTOMERS_CSV)])
    assert [d["name"] for d in created] == ["orders", "customers"]


def test_approve_then_retry_is_refused(client):
    [created] = upload(client, [("orders.csv", ORDERS_CSV)])
    approved = client.post(f"/api/datasets/{created['id']}/approve").json()
    assert approved["status"] == "approved"
    # Only failed datasets can be retried
    assert client.post(f"/api/datasets/{created['id']}/retry").status_code == 409


def test_interrupted_dataset_can_be_retried(client, db):
    [created] = upload(client, [("orders.csv", ORDERS_CSV)])

    # Simulate a job the server died in the middle of
    ds = db.get(ingestion.Dataset, created["id"])
    ds.status, ds.progress, ds.stage = "processing", 40, "Reading files"
    db.commit()

    # A fresh start sweeps it up...
    with ingestion.SessionLocal() as session:
        assert ingestion.fail_interrupted_datasets(session) >= 1
    failed = client.get(f"/api/datasets/{created['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error"] == ingestion.INTERRUPTED_ERROR

    # ...and the user can retry, which re-runs the pipeline from the stored raw files
    retried = client.post(f"/api/datasets/{created['id']}/retry")
    assert retried.status_code == 200
    assert client.get(f"/api/datasets/{created['id']}").json()["status"] == "needs_review"
