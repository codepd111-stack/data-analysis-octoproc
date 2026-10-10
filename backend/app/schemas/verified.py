from datetime import datetime

from app.schemas.base import CamelModel


class VerifiedQueryOut(CamelModel):
    id: str
    dataset_id: str
    question: str
    sql: str
    # True when the question was asked without earlier turns, so it can be reused on its own
    standalone: bool
    conversation_id: str | None = None
    created_at: datetime
