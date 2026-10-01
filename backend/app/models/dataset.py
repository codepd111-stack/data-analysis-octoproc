from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, JSONType
from app.core.utils import new_id, utcnow


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    raw_key: Mapped[str] = mapped_column(String(512))
    parquet_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)

    # processing | needs_review | approved | failed
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Column statistics produced by profiling (used to build prompts later)
    profile: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SemanticLayer(Base):
    """One row per saved version. Approval is per version; chat uses the latest approved one."""

    __tablename__ = "semantic_layers"
    __table_args__ = (UniqueConstraint("dataset_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    layer: Mapped[dict] = mapped_column(JSONType)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)