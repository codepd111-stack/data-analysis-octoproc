import pytest

from app.api.insights import _spreadsheet_safe
from app.core.config import settings


def test_health_checks_the_database(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "connected"}


def test_cors_origin_list_trims_and_strips_trailing_slashes(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", " https://app.example.com/ ,http://localhost:3000,, ")
    assert settings.cors_origin_list == ["https://app.example.com", "http://localhost:3000"]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("=SUM(A1)", "'=SUM(A1)"),
        ("+1", "'+1"),
        ("-5", "'-5"),
        ("@cmd", "'@cmd"),
        ("hello", "hello"),
        (None, ""),
        (12, "12"),
    ],
)
def test_csv_cells_cannot_become_formulas(value, expected):
    assert _spreadsheet_safe(value) == expected


def test_insights_endpoints(client):
    summary = client.get("/api/insights/summary").json()
    assert isinstance(summary["total"], int)

    export = client.get("/api/insights/export")
    assert export.status_code == 200
    assert export.text.startswith("﻿created_at,dataset,question,")
    assert "attachment" in export.headers["content-disposition"]

    assert client.get("/api/insights/logs?filter=bogus").status_code == 400
    assert client.get("/api/insights/logs?filter=failed").json()["items"] == []
