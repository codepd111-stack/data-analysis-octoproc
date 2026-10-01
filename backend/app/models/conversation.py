from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType
from app.core.utils import new_id, utcnow


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    dataset: Mapped["Dataset"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        order_by="Message.created_at", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    chart: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)  # up | down
    feedback_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QueryLog(Base):
    """
    One row per question answered. Foreign keys are SET NULL on delete so that
    logs survive when a user deletes a conversation: they feed system improvement.
    """

    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)