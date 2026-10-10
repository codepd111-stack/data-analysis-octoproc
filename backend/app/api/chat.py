import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import utcnow
from app.models.conversation import Conversation, Message, QueryLog
from app.models.dataset import Dataset
from app.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest, MessageOut
from app.schemas.semantic import SemanticLayerSchema
from app.services.chat_orchestrator import answer_question
from app.services.semantic_store import latest_approved_layer
from app.services.verified_store import forget_from_message, load_examples, remember

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, req.dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found")
    if dataset.status != "approved":
        raise HTTPException(409, "This dataset has not been approved for chat yet.")
    layer_row = latest_approved_layer(db, dataset.id)
    if layer_row is None:
        raise HTTPException(409, "No approved semantic layer found for this dataset.")
    dataset_id = dataset.id

    if req.conversation_id:
        conversation = db.get(Conversation, req.conversation_id)
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        if conversation.dataset_id != dataset.id:
            raise HTTPException(400, "Conversation belongs to a different dataset.")
    else:
        conversation = Conversation(dataset_id=dataset.id, title=req.question.strip()[:60])
        db.add(conversation)
        db.flush()

    # Earlier turns (before this question), including the SQL used, so follow-ups work
    history = [
        {"role": m.role, "content": m.content, "sql": m.sql} for m in conversation.messages
    ]

    db.add(Message(conversation_id=conversation.id, role="user", content=req.question))
    db.flush()

    started = time.perf_counter()
    result = answer_question(
        dataset=dataset,
        layer=SemanticLayerSchema.model_validate(layer_row.layer),
        history=history,
        question=req.question,
        verified=load_examples(db, dataset.id),
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    if result.retry_after is not None:
        # Rate-limited by the AI service: keep the conversation clean (discard this turn),
        # record the event for the insights page, and tell the client when to retry.
        db.rollback()
        db.add(
            QueryLog(
                dataset_id=dataset_id,
                question=req.question,
                generated_sql=result.sql,
                attempts=result.attempts,
                success=False,
                error=result.error,
                latency_ms=latency_ms,
                model=result.model,
            )
        )
        db.commit()
        return JSONResponse(
            status_code=429,
            content={"detail": result.content, "retryAfter": result.retry_after},
            headers={"Retry-After": str(result.retry_after)},
        )

    assistant = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.content,
        chart=result.chart,
        sql=result.sql,
        trust=result.trust,
        grounding=result.grounding,
    )
    db.add(assistant)
    db.flush()

    db.add(
        QueryLog(
            conversation_id=conversation.id,
            message_id=assistant.id,
            dataset_id=dataset_id,
            question=req.question,
            generated_sql=result.sql,
            attempts=result.attempts,
            success=result.success,
            error=result.error,
            row_count=result.row_count,
            latency_ms=latency_ms,
            model=result.model,
            trust=result.trust,
        )
    )
    conversation.updated_at = utcnow()
    db.commit()
    db.refresh(assistant)

    return ChatResponse(conversation_id=conversation.id, message=MessageOut.model_validate(assistant))


@router.post("/feedback", status_code=204)
def feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    message = db.get(Message, req.message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(404, "Message not found")
    message.feedback = req.feedback
    # A reason only makes sense for a thumbs-down
    message.feedback_reason = req.reason if req.feedback == "down" else None

    # A thumbs-up is a person confirming the calculation, so it joins the verified library;
    # taking the thumbs-up back removes it again.
    log = db.scalar(select(QueryLog).where(QueryLog.message_id == message.id))
    if req.feedback == "up" and log is not None and log.success and log.dataset_id and message.sql:
        earlier = db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == message.conversation_id,
                Message.created_at < message.created_at,
            )
        )
        remember(
            db,
            dataset_id=log.dataset_id,
            question=log.question,
            sql=message.sql,
            standalone=(earlier or 0) <= 1,  # only its own question came before it
            message_id=message.id,
        )
    else:
        forget_from_message(db, message.id)
    db.commit()
