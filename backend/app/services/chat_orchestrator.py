import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.models.dataset import Dataset
from app.schemas.chat import GroundingSchema
from app.schemas.semantic import FilterSchema, SemanticLayerSchema
from app.services import prompts
from app.services.chart_builder import build_chart
from app.services.dataset_tables import get_table_paths
from app.services.grounding import assess, missing_filters
from app.services.llm_client import LLMError, get_llm
from app.services.query_engine import (
    QueryError,
    QueryResult,
    ValidatedQuery,
    run_query,
    validate_select,
)
from app.services.schema_context import build_schema_prompt
from app.services.verified_store import (
    VerifiedExample,
    exact_match,
    match_sql,
    pick_examples,
)

logger = logging.getLogger(__name__)

MAX_SQL_RETRIES = 2  # up to 3 attempts in total
HISTORY_TURNS = 3
ROWS_FOR_NARRATIVE = 40
DEFAULT_RETRY_SECONDS = 30
EXAMPLE_SQL_CHARS = 1200


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
    trust: str | None = None  # verified | governed | ad_hoc, only when a query ran
    grounding: dict | None = None  # GroundingSchema shape, camelCase keys


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


def _examples_block(examples: list[VerifiedExample]) -> str:
    if not examples:
        return ""
    lines = ["VERIFIED EXAMPLES (SQL a person confirmed as correct for this dataset)"]
    for ex in examples:
        lines.append(f"Q: {ex.question[:300]}")
        lines.append(f"SQL: {ex.sql[:EXAMPLE_SQL_CHARS]}")
    return "\n".join(lines) + "\n\n"


def _compose_user_prompt(
    schema: str, examples: list[VerifiedExample], history: list[dict], question: str
) -> str:
    return (
        f"Today's date: {date.today().isoformat()}\n\n"
        f"{schema}\n\n"
        f"{_examples_block(examples)}"
        f"{_history_block(history)}"
        f"QUESTION: {question}"
    )


def _skipped_filters(plan: dict) -> dict[str, str]:
    """{filter id: reason} from the model's reply, ignoring anything malformed."""
    out: dict[str, str] = {}
    raw = plan.get("skipped_filters")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out[item["id"]] = _clean(item.get("reason")) or "the user asked to include those rows"
    return out


def _filter_feedback(missing: list[FilterSchema]) -> str:
    lines = []
    for f in missing:
        line = f"- table {f.table}: {f.expression}  (id={f.id}"
        line += f", {f.description})" if f.description else ")"
        lines.append(line)
    return (
        "The query reads a table without applying its default filter:\n"
        + "\n".join(lines)
        + "\nAdd each expression exactly as written to the WHERE clause of the SELECT or CTE that "
        "reads that table. Only if the user explicitly asked to include those rows, leave the "
        'filter out and list it in "skipped_filters" with the reason. '
        "Return the full JSON object again."
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


def _narrative_from_model(
    question: str, assumptions: str, layer: SemanticLayerSchema, result: QueryResult
) -> str:
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


def _narrate(
    question: str,
    plan: dict,
    layer: SemanticLayerSchema,
    result: QueryResult,
    grounding: GroundingSchema,
) -> str:
    """LLM call 2. Never raises: falls back to a plain summary of the rows."""
    assumptions = _clean(plan.get("assumptions"))
    for f in grounding.filters_skipped:
        assumptions += (
            f" Rows normally left out ({f.description or f.expression}) were included "
            f"because {f.reason}."
        )
    assumptions = assumptions.strip()

    if result.row_count == 0:
        text = "I couldn't find any data matching that question."
        text = f"{text} {assumptions}" if assumptions else text
    else:
        text = _narrative_from_model(question, assumptions, layer, result)

    # A default filter the model left out on its own: say so where it will actually be read
    if grounding.filters_missing:
        rules = "; ".join(f.description or f.expression for f in grounding.filters_missing)
        text += (
            f'\n\nNote: the usual rule "{rules}" was not applied to this answer, '
            "so treat it with care."
        )
    return text


# ---------- the pipeline ----------


def answer_question(
    *,
    dataset: Dataset,
    layer: SemanticLayerSchema,
    history: list[dict],
    question: str,
    verified: list[VerifiedExample] | None = None,
) -> AnswerResult:
    """Never raises: the chat endpoint always receives an answer object to store and return."""
    try:
        return _answer(
            dataset=dataset,
            layer=layer,
            history=history,
            question=question,
            verified=verified or [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected failure while answering")
        return AnswerResult(
            content="Something went wrong while analysing your question. Please try again.",
            success=False,
            error=f"internal: {exc}"[:500],
        )


def _finish(
    *,
    question: str,
    layer: SemanticLayerSchema,
    validated: ValidatedQuery,
    result: QueryResult,
    plan: dict,
    attempts: int,
    model: str | None,
    verified: list[VerifiedExample],
) -> AnswerResult:
    """Grade the answer (trust badge and receipts), narrate it and build the chart."""
    known = match_sql(verified, validated.sql)
    trust, grounding = assess(
        sql=validated.sql,
        layer=layer,
        tables_read=validated.tables,
        result=result,
        skipped=_skipped_filters(plan),
        verified_question=known.question if known else None,
    )
    return AnswerResult(
        content=_narrate(question, plan, layer, result, grounding),
        chart=build_chart(result, plan.get("chart")),
        sql=validated.sql,
        attempts=attempts,
        success=True,
        row_count=result.row_count,
        model=model,
        trust=trust,
        grounding=grounding.model_dump(by_alias=True),
    )


def _from_library(
    known: VerifiedExample,
    layer: SemanticLayerSchema,
    table_paths: dict[str, Path],
    allowed: set[str],
    question: str,
) -> AnswerResult | None:
    """
    Answer a question a person already verified, without asking the model. None when the stored
    SQL no longer runs, or when a default filter was added since: then it is no longer the agreed
    calculation and the model gets to redo it.
    """
    try:
        validated = validate_select(known.sql, allowed)
        result = run_query({t: table_paths[t] for t in validated.tables}, validated.sql)
    except QueryError as exc:
        logger.info("Verified SQL no longer runs (%s); asking the model instead", exc)
        return None
    if missing_filters(validated.sql, layer, validated.tables, set()):
        return None
    return _finish(
        question=question,
        layer=layer,
        validated=validated,
        result=result,
        plan={},
        attempts=0,
        model=None,
        verified=[known],
    )


def _answer(
    *,
    dataset: Dataset,
    layer: SemanticLayerSchema,
    history: list[dict],
    question: str,
    verified: list[VerifiedExample],
) -> AnswerResult:
    table_paths = get_table_paths(dataset, {t.name for t in layer.tables})
    if not table_paths:
        return AnswerResult(
            content="I couldn't find the stored data for this dataset. Please upload it again.",
            success=False,
            error="data_missing",
        )
    allowed = set(table_paths)

    # A question a person already verified, asked afresh: reuse the confirmed SQL as it is
    if not history:
        known = exact_match(verified, question)
        if known is not None and known.standalone:
            answer = _from_library(known, layer, table_paths, allowed, question)
            if answer is not None:
                return answer

    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompts.SQL_GENERATION_SYSTEM},
        {
            "role": "user",
            "content": _compose_user_prompt(
                build_schema_prompt(dataset, layer, allowed),
                pick_examples(verified, question),
                history,
                question,
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
    filter_retry_used = False

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

        # Guardrail: a default filter left out without the user asking is sent back once.
        # If the model still leaves it out, the answer is kept but flagged (see grounding).
        missing = missing_filters(
            validated.sql, layer, validated.tables, set(_skipped_filters(plan))
        )
        if missing and not filter_retry_used and attempt <= MAX_SQL_RETRIES:
            filter_retry_used = True
            logger.info("Attempt %s left out default filters %s", attempt, [f.id for f in missing])
            messages.append({"role": "user", "content": _filter_feedback(missing)})
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
    return _finish(
        question=question,
        layer=layer,
        validated=validated,
        result=result,
        plan=plan,
        attempts=attempts,
        model=model_used,
        verified=verified,
    )
