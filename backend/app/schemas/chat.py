from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.base import CamelModel

FeedbackReason = Literal["wrong_numbers", "wrong_chart", "misunderstood", "too_vague", "other"]

# verified = a person confirmed this exact calculation before; governed = built only from approved
# metrics with every default filter applied; ad_hoc = the model's own calculation
Trust = Literal["verified", "governed", "ad_hoc"]


class ChartSpecSchema(CamelModel):
    type: Literal["bar", "line", "pie"]
    title: str
    x_key: str
    y_keys: list[str]
    data: list[dict[str, str | int | float]]


class MetricUse(CamelModel):
    name: str
    expression: str


class FilterUse(CamelModel):
    id: str
    table: str
    expression: str
    description: str = ""
    reason: str | None = None  # for a skipped filter: why the user wanted those rows included


class GroundingSchema(CamelModel):
    """The receipts behind an answer: what it was built from, and why it got its trust badge."""

    reason: str
    metrics_used: list[MetricUse] = Field(default_factory=list)
    filters_applied: list[FilterUse] = Field(default_factory=list)
    filters_skipped: list[FilterUse] = Field(default_factory=list)
    filters_missing: list[FilterUse] = Field(default_factory=list)
    unmatched_aggregates: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows_preview: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    verified_question: str | None = None


class MessageOut(CamelModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    chart: ChartSpecSchema | None = None
    sql: str | None = None
    feedback: str | None = None
    feedback_reason: str | None = None
    trust: Trust | None = None
    grounding: GroundingSchema | None = None
    created_at: datetime


class ChatRequest(CamelModel):
    dataset_id: str
    conversation_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)


class ChatResponse(CamelModel):
    conversation_id: str
    message: MessageOut


class FeedbackRequest(CamelModel):
    message_id: str
    feedback: Literal["up", "down"] | None = None
    reason: FeedbackReason | None = None


class ConversationOut(CamelModel):
    id: str
    title: str
    dataset_id: str
    dataset_name: str
    updated_at: datetime
    message_count: int
    preview: str


class ConversationPage(CamelModel):
    items: list[ConversationOut]
    total: int


class ConversationDetail(CamelModel):
    conversation: ConversationOut
    messages: list[MessageOut]
