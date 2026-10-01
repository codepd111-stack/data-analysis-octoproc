from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

FeedbackReason = Literal["wrong_numbers", "wrong_chart", "misunderstood", "too_vague", "other"]


class ChartSpecSchema(CamelModel):
    type: Literal["bar", "line", "pie"]
    title: str
    x_key: str
    y_keys: list[str]
    data: list[dict[str, str | int | float]]


class MessageOut(CamelModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    chart: ChartSpecSchema | None = None
    sql: str | None = None
    feedback: str | None = None
    feedback_reason: str | None = None
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