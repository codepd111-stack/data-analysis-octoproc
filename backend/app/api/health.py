from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_auth
from app.core.database import get_db
from app.services.llm_client import LLMError, get_llm

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/llm", dependencies=[Depends(require_auth)])
def health_llm():
    try:
        result = get_llm().chat(
            [{"role": "user", "content": "Reply with the single word: pong"}], max_tokens=200
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "model": result.model, "reply": result.text.strip()}