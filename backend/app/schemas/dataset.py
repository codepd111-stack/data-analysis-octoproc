from datetime import datetime

from app.core.utils import format_bytes
from app.models.dataset import Dataset
from app.schemas.base import CamelModel


class DatasetOut(CamelModel):
    id: str
    name: str
    file_name: str
    rows: int
    columns: int
    table_count: int = 0
    size_label: str
    status: str
    uploaded_at: datetime
    progress: int | None = None
    stage: str | None = None
    error: str | None = None

    @classmethod
    def from_model(cls, d: Dataset) -> "DatasetOut":
        tables = (d.profile or {}).get("tables")
        table_count = len(tables) if tables else (1 if d.table_name else 0)
        return cls(
            id=d.id,
            name=d.name,
            file_name=d.file_name,
            rows=d.row_count,
            columns=d.column_count,
            table_count=table_count,
            size_label=format_bytes(d.size_bytes),
            status=d.status,
            uploaded_at=d.created_at,
            progress=d.progress,
            stage=d.stage,
            error=d.error,
        )