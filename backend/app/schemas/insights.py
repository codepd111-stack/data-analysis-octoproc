from datetime import datetime
from typing import Literal

from app.schemas.base import CamelModel


class ErrorCount(CamelModel):
    error: str
    count: int


class InsightsSummary(CamelModel):
    days: int | None = None
    total: int
    answered: int
    failed: int
    unanswerable: int
    retried: int
    rate_limited: int
    avg_latency_ms: int | None = None
    thumbs_up: int
    thumbs_down: int
    # Answered questions by trust badge
    verified: int = 0
    governed: int = 0
    ad_hoc: int = 0
    top_errors: list[ErrorCount]


class LogEntry(CamelModel):
    id: str
    created_at: datetime
    question: str
    status: Literal["ok", "retried", "failed", "unanswerable", "rate_limited"]
    attempts: int
    latency_ms: int | None = None
    row_count: int | None = None
    model: str | None = None
    sql: str | None = None
    error: str | None = None
    feedback: str | None = None
    feedback_reason: str | None = None
    trust: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    conversation_id: str | None = None


class LogPage(CamelModel):
    items: list[LogEntry]
    total: int


class QualityIssue(CamelModel):
    severity: Literal["warning", "info"]
    table: str
    column: str | None = None
    message: str
