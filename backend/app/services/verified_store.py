"""
The verified-answer library: questions whose SQL a person confirmed with a thumbs-up in chat.
It is used in two ways: as worked examples in the SQL prompt, and to label an answer Verified
when it repeats a confirmed calculation (or, for a fresh chat, to answer without the model).
"""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import utcnow
from app.models.conversation import Message
from app.models.dataset import VerifiedQuery

MAX_EXAMPLES = 3
MIN_SIMILARITY = 0.2
QUESTION_NORM_CHARS = 500
# Words that say nothing about what is being asked
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "by", "to", "at", "and", "or", "is", "are", "was",
    "were", "be", "do", "does", "did", "what", "whats", "which", "how", "show", "me", "give",
    "get", "please", "can", "you", "i", "we", "our", "my", "this", "that", "it", "its", "with",
    "from", "per", "each", "there", "their", "them", "have", "has", "had",
}


@dataclass
class VerifiedExample:
    id: str
    question: str
    sql: str
    standalone: bool
    question_norm: str
    sql_norm: str


def normalize_question(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))[:QUESTION_NORM_CHARS]


def normalize_sql(sql: str) -> str:
    """Formatting-independent text for a query, so a re-generated answer can be recognised."""
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except SqlglotError:
        return " ".join(sql.split()).lower()
    for ident in tree.find_all(exp.Identifier):
        ident.set("this", ident.this.lower())
    # The row cap the validator adds is not part of the calculation
    limit = tree.args.get("limit")
    if isinstance(limit, exp.Limit) and limit.expression.sql() == str(settings.max_query_rows):
        tree.set("limit", None)
    return tree.sql(dialect="duckdb")


def example(question: str, sql: str, *, standalone: bool = True, id: str = "") -> VerifiedExample:
    return VerifiedExample(
        id=id,
        question=question,
        sql=sql,
        standalone=standalone,
        question_norm=normalize_question(question),
        sql_norm=normalize_sql(sql),
    )


# ---------- matching (pure, used by the chat pipeline) ----------


def _words(norm: str) -> set[str]:
    return {w for w in norm.split() if w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Share of meaningful words two normalised questions have in common (0 to 1)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def exact_match(examples: list[VerifiedExample], question: str) -> VerifiedExample | None:
    norm = normalize_question(question)
    return next((e for e in examples if e.question_norm == norm), None)


def match_sql(examples: list[VerifiedExample], sql: str) -> VerifiedExample | None:
    norm = normalize_sql(sql)
    return next((e for e in examples if e.sql_norm == norm), None)


def pick_examples(
    examples: list[VerifiedExample], question: str, limit: int = MAX_EXAMPLES
) -> list[VerifiedExample]:
    """The most similar verified questions, best first; an identical question always leads."""
    norm = normalize_question(question)
    scored = [
        (1.0 if e.question_norm == norm else similarity(e.question_norm, norm), e)
        for e in examples
    ]
    kept = [(s, e) for s, e in scored if s >= MIN_SIMILARITY]
    kept.sort(key=lambda pair: pair[0], reverse=True)  # stable: newer entries win ties
    return [e for _, e in kept[:limit]]


# ---------- storage ----------


def load_examples(db: Session, dataset_id: str) -> list[VerifiedExample]:
    stmt = (
        select(VerifiedQuery)
        .where(VerifiedQuery.dataset_id == dataset_id)
        .order_by(VerifiedQuery.created_at.desc())
    )
    return [
        VerifiedExample(
            id=r.id,
            question=r.question,
            sql=r.sql,
            standalone=r.standalone,
            question_norm=r.question_norm,
            sql_norm=r.sql_norm,
        )
        for r in db.scalars(stmt).all()
    ]


def list_for_dataset(db: Session, dataset_id: str) -> list[tuple[VerifiedQuery, str | None]]:
    """Entries with the conversation they came from (None once that conversation is deleted)."""
    stmt = (
        select(VerifiedQuery, Message.conversation_id)
        .outerjoin(Message, VerifiedQuery.source_message_id == Message.id)
        .where(VerifiedQuery.dataset_id == dataset_id)
        .order_by(VerifiedQuery.created_at.desc())
    )
    return [(row, conversation_id) for row, conversation_id in db.execute(stmt).all()]


def remember(
    db: Session, *, dataset_id: str, question: str, sql: str, standalone: bool, message_id: str
) -> VerifiedQuery:
    """Add the question, or replace the SQL of an entry for the same question. Caller commits."""
    question_norm = normalize_question(question)
    row = db.scalar(
        select(VerifiedQuery).where(
            VerifiedQuery.dataset_id == dataset_id, VerifiedQuery.question_norm == question_norm
        )
    )
    if row is None:
        row = VerifiedQuery(dataset_id=dataset_id, question_norm=question_norm)
        db.add(row)
    row.question = question.strip()
    row.sql = sql
    row.sql_norm = normalize_sql(sql)
    row.standalone = standalone
    row.source_message_id = message_id
    row.created_at = utcnow()
    db.flush()
    return row


def forget_from_message(db: Session, message_id: str) -> int:
    """Remove the entry a message created (its thumbs-up was taken back). Caller commits."""
    rows = db.scalars(
        select(VerifiedQuery).where(VerifiedQuery.source_message_id == message_id)
    ).all()
    for row in rows:
        db.delete(row)
    return len(rows)
