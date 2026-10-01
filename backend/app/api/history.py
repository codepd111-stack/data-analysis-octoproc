from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.conversation import Conversation, Message
from app.models.dataset import Dataset
from app.schemas.chat import ConversationDetail, ConversationOut, ConversationPage, MessageOut

router = APIRouter(prefix="/api/history", tags=["history"])


def _to_out(c: Conversation) -> ConversationOut:
    last = c.messages[-1] if c.messages else None
    return ConversationOut(
        id=c.id,
        title=c.title,
        dataset_id=c.dataset_id,
        dataset_name=c.dataset.name,
        updated_at=c.updated_at,
        message_count=len(c.messages),
        preview=last.content[:140] if last else "",
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=ConversationPage)
def list_conversations(
    q: str | None = Query(None, max_length=100),
    dataset_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    if dataset_id:
        conditions.append(Conversation.dataset_id == dataset_id)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        message_match = exists().where(
            Message.conversation_id == Conversation.id,
            Message.content.ilike(pattern, escape="\\"),
        )
        conditions.append(
            or_(
                Conversation.title.ilike(pattern, escape="\\"),
                Dataset.name.ilike(pattern, escape="\\"),
                message_match,
            )
        )

    total = db.scalar(
        select(func.count(Conversation.id))
        .select_from(Conversation)
        .join(Dataset, Conversation.dataset_id == Dataset.id)
        .where(*conditions)
    )

    stmt = (
        select(Conversation)
        .join(Dataset, Conversation.dataset_id == Dataset.id)
        .where(*conditions)
        .options(selectinload(Conversation.messages), selectinload(Conversation.dataset))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [_to_out(c) for c in db.scalars(stmt).all()]
    return ConversationPage(items=items, total=total or 0)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return ConversationDetail(
        conversation=_to_out(conversation),
        messages=[MessageOut.model_validate(m) for m in conversation.messages],
    )


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    db.delete(conversation)  # query logs are kept (their foreign keys are set to NULL)
    db.commit()