import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import utcnow
from app.models.conversation import Message, QueryLog
from app.models.dataset import Dataset
from app.schemas.insights import ErrorCount, InsightsSummary, LogEntry, LogPage

router = APIRouter(prefix="/api/insights", tags=["insights"])

FILTERS = {"attention", "failed", "downvoted", "retried", "unanswerable", "rate_limited", "all"}

IS_UNANSWERABLE = QueryLog.error == "unanswerable"
IS_RATE_LIMITED = QueryLog.error.like("rate_limited%")
IS_FAILED = and_(
    QueryLog.success.is_(False),
    or_(
        QueryLog.error.is_(None),
        and_(QueryLog.error != "unanswerable", ~QueryLog.error.like("rate_limited%")),
    ),
)
IS_RETRIED = and_(QueryLog.success.is_(True), QueryLog.attempts >= 2)
IS_DOWN = Message.feedback == "down"


def _count(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _conditions(filter_name: str, days: int | None) -> list:
    conditions: list = []
    if days:
        conditions.append(QueryLog.created_at >= utcnow() - timedelta(days=days))
    if filter_name == "attention":
        conditions.append(or_(IS_FAILED, IS_RETRIED, IS_DOWN))
    elif filter_name == "failed":
        conditions.append(IS_FAILED)
    elif filter_name == "downvoted":
        conditions.append(IS_DOWN)
    elif filter_name == "retried":
        conditions.append(IS_RETRIED)
    elif filter_name == "unanswerable":
        conditions.append(IS_UNANSWERABLE)
    elif filter_name == "rate_limited":
        conditions.append(IS_RATE_LIMITED)
    return conditions


def _status(log: QueryLog) -> str:
    error = log.error or ""
    if error == "unanswerable":
        return "unanswerable"
    if error.startswith("rate_limited"):
        return "rate_limited"
    if not log.success:
        return "failed"
    return "retried" if log.attempts >= 2 else "ok"


def _entry(log: QueryLog, feedback: str | None, reason: str | None, dataset_name: str | None) -> LogEntry:
    return LogEntry(
        id=log.id,
        created_at=log.created_at,
        question=log.question,
        status=_status(log),
        attempts=log.attempts,
        latency_ms=log.latency_ms,
        row_count=log.row_count,
        model=log.model,
        sql=log.generated_sql,
        error=log.error,
        feedback=feedback,
        feedback_reason=reason,
        dataset_id=log.dataset_id,
        dataset_name=dataset_name,
        conversation_id=log.conversation_id,
    )


def _log_rows_stmt():
    return (
        select(QueryLog, Message.feedback, Message.feedback_reason, Dataset.name)
        .outerjoin(Message, QueryLog.message_id == Message.id)
        .outerjoin(Dataset, QueryLog.dataset_id == Dataset.id)
    )


def _check_filter(name: str) -> str:
    if name not in FILTERS:
        raise HTTPException(400, f"Unknown filter. Use one of: {', '.join(sorted(FILTERS))}")
    return name


@router.get("/summary", response_model=InsightsSummary)
def summary(days: int | None = Query(None, ge=1, le=365), db: Session = Depends(get_db)):
    window = _conditions("all", days)

    row = db.execute(
        select(
            func.count(QueryLog.id),
            _count(QueryLog.success.is_(True)),
            _count(IS_FAILED),
            _count(IS_UNANSWERABLE),
            _count(IS_RETRIED),
            _count(IS_RATE_LIMITED),
            func.avg(case((QueryLog.success.is_(True), QueryLog.latency_ms))),
        ).where(*window)
    ).one()

    ratings = db.execute(
        select(_count(Message.feedback == "up"), _count(Message.feedback == "down"))
        .select_from(QueryLog)
        .join(Message, QueryLog.message_id == Message.id)
        .where(*window)
    ).one()

    error_expr = func.substr(QueryLog.error, 1, 100)
    top = db.execute(
        select(error_expr, func.count())
        .where(*window, IS_FAILED)
        .group_by(error_expr)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    return InsightsSummary(
        days=days,
        total=int(row[0]),
        answered=int(row[1]),
        failed=int(row[2]),
        unanswerable=int(row[3]),
        retried=int(row[4]),
        rate_limited=int(row[5]),
        avg_latency_ms=int(round(float(row[6]))) if row[6] is not None else None,
        thumbs_up=int(ratings[0]),
        thumbs_down=int(ratings[1]),
        top_errors=[ErrorCount(error=e or "(no message)", count=int(c)) for e, c in top],
    )


@router.get("/logs", response_model=LogPage)
def logs(
    status_filter: str = Query("attention", alias="filter"),
    days: int | None = Query(None, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = _conditions(_check_filter(status_filter), days)

    total = db.scalar(
        select(func.count(QueryLog.id))
        .select_from(QueryLog)
        .outerjoin(Message, QueryLog.message_id == Message.id)
        .where(*conditions)
    )
    rows = db.execute(
        _log_rows_stmt()
        .where(*conditions)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return LogPage(items=[_entry(*r) for r in rows], total=total or 0)


def _spreadsheet_safe(value: object) -> str:
    """Stop spreadsheet apps from treating user text such as '=SUM(...)' as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get("/export")
def export_csv(
    status_filter: str = Query("all", alias="filter"),
    days: int | None = Query(None, ge=1, le=365),
    db: Session = Depends(get_db),
):
    conditions = _conditions(_check_filter(status_filter), days)
    rows = db.execute(
        _log_rows_stmt().where(*conditions).order_by(QueryLog.created_at.desc()).limit(5000)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at", "dataset", "question", "status", "attempts", "latency_ms",
            "row_count", "model", "feedback", "feedback_reason", "sql", "error",
        ]
    )
    for log, feedback, reason, dataset_name in rows:
        writer.writerow(
            [
                _spreadsheet_safe(v)
                for v in (
                    log.created_at.isoformat(), dataset_name, log.question, _status(log),
                    log.attempts, log.latency_ms, log.row_count, log.model, feedback, reason,
                    log.generated_sql, log.error,
                )
            ]
        )

    return Response(
        content="\ufeff" + buffer.getvalue(),  # BOM so Excel reads UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="octoproc-query-logs.csv"'},
    )