import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.models.dataset import Dataset
from app.schemas.semantic import SemanticLayerSchema
from app.services import prompts
from app.services.chart_builder import build_chart
from app.services.dataset_tables import get_table_profiles
from app.services.llm_client import LLMError, get_llm
from app.services.query_engine import (
    QueryError,
    QueryResult,
    ValidatedQuery,
    run_query,
    validate_select,
)
from app.services.schema_context import build_schema_prompt
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

MAX_SQL_RETRIES = 2  # up to 3 attempts in total
HISTORY_TURNS = 3
ROWS_FOR_NARRATIVE = 40
DEFAULT_RETRY_SECONDS = 30


@dataclass
class AnswerResult:
    content: str
    chart: dict | None = None  # ChartSpec shape, camelCase keys
    sql: str | None = None
    attempts: int = 0
    success: bool = True
    error: str | None = None
    row_count: int | None = None
    model: str | None = None
    retry_after: int | None = None  # set only when the AI service rate-limited us


# ---------- small helpers ----------


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_rate_limit(text: str) -> bool:
    t = text.lower()
    return (
        "error code: 429" in t
        or "rate limit" in t
        or "rate_limit" in t
        or "too many requests" in t
    )


def parse_retry_after(text: str) -> int | None:
    """Groq says things like 'Please try again in 6m5.472s', '12.5s' or '340ms'."""
    match = re.search(r"try again in\s+([0-9hms.]+)", text, re.IGNORECASE)
    if not match:
        return None
    total = 0.0
    for number, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", match.group(1)):
        value = float(number)
        total += value / 1000 if unit == "ms" else value * {"h": 3600, "m": 60, "s": 1}[unit]
    if total <= 0:
        return None
    return max(1, min(int(math.ceil(total)), 3600))


def _llm_failure_message(text: str) -> str:
    if _is_rate_limit(text):
        return "The AI service has hit its rate limit. Please wait a moment and try again."
    if "GROQ_API_KEY" in text:
        return "The AI service is not configured (missing API key)."
    return "The AI service had a problem answering. Please try again in a moment."


def _retry_message(error: str) -> str:
    return (
        f"That query could not be used: {error}\n"
        "Fix the problem and return the full JSON object again."
    )


def _table_paths(dataset: Dataset, layer: SemanticLayerSchema) -> dict[str, Path]:
    storage = get_storage()
    wanted = {t.name for t in layer.tables}
    paths: dict[str, Path] = {}
    for prof in get_table_profiles(dataset):
        name, key = prof.get("table"), prof.get("parquetKey")
        if not name or not key or name not in wanted:
            continue
        try:
            path = storage.get_local_path(key)
        except FileNotFoundError:
            continue
        if path.exists():
            paths[name] = path
    return paths


def _history_block(history: list[dict]) -> str:
    recent = history[-(HISTORY_TURNS * 2) :]
    if not recent:
        return ""
    lines: list[str] = []
    for m in recent:
        text = str(m.get("content") or "")[:300]
        if m.get("role") == "user":
            lines.append(f"User asked: {text}")
        else:
            lines.append(f"Answer given: {text}")
            if m.get("sql"):
                lines.append(f"SQL used: {str(m['sql'])[:800]}")
    return "CONVERSATION SO FAR (oldest first)\n" + "\n".join(lines) + "\n\n"


def _compose_user_prompt(schema: str, history: list[dict], question: str) -> str:
    return (
        f"Today's date: {date.today().isoformat()}\n\n"
        f"{schema}\n\n"
        f"{_history_block(history)}"
        f"QUESTION: {question}"
    )


# ---------- LLM calls ----------


def _plan(messages: list[dict[str, str]]):
    """LLM call 1. Uses the main model; on a rate limit, retries once with the small model."""
    llm = get_llm()
    kwargs = {"reasoning_effort": "medium", "max_tokens": 3500}
    try:
        return llm.chat_json(messages, model=settings.groq_model_main, **kwargs)
    except LLMError as exc:
        if _is_rate_limit(str(exc)) and settings.groq_model_fast != settings.groq_model_main:
            logger.warning("Main model rate-limited; retrying with %s", settings.groq_model_fast)
            return llm.chat_json(messages, model=settings.groq_model_fast, **kwargs)
        raise


def _fallback_narrative(result: QueryResult) -> str:
    if result.row_count == 0:
        return "No matching data was found for that question."
    first = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in result.rows[0].items())
    if result.row_count == 1:
        return f"Result: {first}."
    return f"The query returned {result.row_count} rows. The first row is {first}."


def _narrate(question: str, plan: dict, layer: SemanticLayerSchema, result: QueryResult) -> str:
    """LLM call 2. Never raises: falls back to a plain summary of the rows."""
    assumptions = _clean(plan.get("assumptions"))

    if result.row_count == 0:
        text = "I couldn't find any data matching that question."
        return f"{text} {assumptions}" if assumptions else text

    shown = result.rows[:ROWS_FOR_NARRATIVE]
    note = ""
    if result.truncated or result.row_count > len(shown):
        note = f" (showing {len(shown)} of {result.row_count} rows)"
    user = (
        f"Dataset: {layer.summary}\n"
        f"Question: {question}\n"
        f"Assumptions: {assumptions or 'none'}\n"
        f"Rows{note}:\n{json.dumps(shown, ensure_ascii=False, default=str)}"
    )
    try:
        res = get_llm().chat(
            [
                {"role": "system", "content": prompts.ANSWER_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=settings.groq_model_fast,
            reasoning_effort="low",
            max_tokens=1500,
            temperature=0.2,
        )
        return res.text.strip() or _fallback_narrative(result)
    except LLMError as exc:
        logger.warning("Narrative step failed, using fallback: %s", exc)
        return _fallback_narrative(result)


# ---------- the pipeline ----------


def answer_question(
    *,
    dataset: Dataset,
    layer: SemanticLayerSchema,
    history: list[dict],
    question: str,
) -> AnswerResult:
    """Never raises: the chat endpoint always receives an answer object to store and return."""
    try:
        return _answer(dataset=dataset, layer=layer, history=history, question=question)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected failure while answering")
        return AnswerResult(
            content="Something went wrong while analysing your question. Please try again.",
            success=False,
            error=f"internal: {exc}"[:500],
        )


def _answer(
    *,
    dataset: Dataset,
    layer: SemanticLayerSchema,
    history: list[dict],
    question: str,
) -> AnswerResult:
    table_paths = _table_paths(dataset, layer)
    if not table_paths:
        return AnswerResult(
            content="I couldn't find the stored data for this dataset. Please upload it again.",
            success=False,
            error="data_missing",
        )
    allowed = set(table_paths)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompts.SQL_GENERATION_SYSTEM},
        {
            "role": "user",
            "content": _compose_user_prompt(
                build_schema_prompt(dataset, layer, allowed), history, question
            ),
        },
    ]

    attempts = 0
    model_used: str | None = None
    last_error = "unknown"
    last_sql: str | None = None
    good: tuple[ValidatedQuery, QueryResult, dict] | None = None
    empty: tuple[ValidatedQuery, QueryResult, dict] | None = None
    zero_retry_used = False

    for attempt in range(1, MAX_SQL_RETRIES + 2):
        attempts = attempt

        try:
            plan, llm_result = _plan(messages)
        except LLMError as exc:
            text = str(exc)
            if ("valid JSON" in text or "empty reply" in text) and attempt <= MAX_SQL_RETRIES:
                last_error = text
                messages += [
                    {"role": "assistant", "content": "{}"},
                    {
                        "role": "user",
                        "content": "That reply was not usable. Return ONLY the JSON object described in the instructions.",
                    },
                ]
                continue

            retry_after: int | None = None
            error = f"llm: {text}"[:500]
            if _is_rate_limit(text):
                retry_after = parse_retry_after(text) or DEFAULT_RETRY_SECONDS
                error = f"rate_limited: retry in {retry_after}s"
            return AnswerResult(
                content=_llm_failure_message(text),
                sql=last_sql,
                attempts=attempts,
                success=False,
                error=error,
                model=model_used,
                retry_after=retry_after,
            )

        if not isinstance(plan, dict):
            plan = {}
        model_used = llm_result.model
        messages.append({"role": "assistant", "content": llm_result.text})

        if plan.get("answerable") is False:
            reason = _clean(plan.get("reason")) or "The data does not contain what is needed."
            return AnswerResult(
                content=f"I can't answer that from this dataset. {reason}",
                attempts=attempts,
                success=False,
                error="unanswerable",
                model=model_used,
            )

        raw_sql = plan.get("sql")
        if not isinstance(raw_sql, str) or not raw_sql.strip():
            last_error = "The reply did not contain a SQL query."
            messages.append({"role": "user", "content": _retry_message(last_error)})
            continue
        last_sql = raw_sql.strip()

        try:
            validated = validate_select(raw_sql, allowed)
            result = run_query({t: table_paths[t] for t in validated.tables}, validated.sql)
        except QueryError as exc:
            last_error = str(exc)
            logger.info("Attempt %s failed: %s", attempt, last_error)
            messages.append({"role": "user", "content": _retry_message(last_error)})
            continue

        if result.row_count == 0:
            empty = (validated, result, plan)
            if not zero_retry_used and attempt <= MAX_SQL_RETRIES:
                zero_retry_used = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The query ran but returned zero rows. Re-check your filter values "
                            "against the sample values and date ranges, and loosen anything too "
                            "strict. Return the full JSON object again. If zero rows really is "
                            "the correct answer, return the same query."
                        ),
                    }
                )
                continue
            break

        good = (validated, result, plan)
        break

    chosen = good or empty
    if chosen is None:
        return AnswerResult(
            content=(
                "I couldn't turn that into a reliable query after a few tries. "
                "Try rephrasing the question or naming the columns you care about."
            ),
            sql=last_sql,
            attempts=attempts,
            success=False,
            error=f"sql_failed: {last_error}"[:500],
            model=model_used,
        )

    validated, result, plan = chosen
    return AnswerResult(
        content=_narrate(question, plan, layer, result),
        chart=build_chart(result, plan.get("chart")),
        sql=validated.sql,
        attempts=attempts,
        success=True,
        row_count=result.row_count,
        model=model_used,
    )