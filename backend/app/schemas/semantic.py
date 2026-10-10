from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

ColumnRole = Literal["identifier", "dimension", "measure", "date"]


class ColumnSchema(CamelModel):
    name: str
    dtype: str
    role: ColumnRole
    description: str = ""
    null_pct: float = 0.0
    distinct: int = 0
    samples: list[str] = Field(default_factory=list)


class TableSchema(CamelModel):
    name: str
    description: str = ""
    columns: list[ColumnSchema]


class RelationshipSchema(CamelModel):
    id: str
    # "from" is a Python keyword, so the field is from_ and the JSON key stays "from"
    from_: str = Field(alias="from")
    to: str
    type: Literal["many-to-one", "one-to-many", "one-to-one"]


class MetricSchema(CamelModel):
    """A governed measure: one aggregate over one table, agreed once and reused in every answer."""

    id: str
    name: str
    table: str
    expression: str  # DuckDB aggregate over the table's columns, e.g. SUM(amount)
    description: str = ""


class FilterSchema(CamelModel):
    """A default filter: the rows an analyst keeps without thinking (no test orders, no deleted rows)."""

    id: str
    table: str
    expression: str  # DuckDB condition that is true for the rows to keep, e.g. status <> 'test'
    description: str = ""


class RuleSchema(CamelModel):
    """A plain-language fact the SQL writer must know, such as "amounts are in EUR including tax"."""

    id: str
    text: str


class SemanticLayerSchema(CamelModel):
    dataset_id: str
    summary: str = ""
    tables: list[TableSchema]
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    # Governed definitions. Layers saved before these existed load with empty lists.
    metrics: list[MetricSchema] = Field(default_factory=list)
    filters: list[FilterSchema] = Field(default_factory=list)
    rules: list[RuleSchema] = Field(default_factory=list)
    # Whether the descriptions came from the AI or from simple name-based guessing
    generated_by: Literal["heuristic", "llm"] = "heuristic"


class DefinitionCheck(CamelModel):
    """What happened when one metric or filter was tried against the real data."""

    id: str
    kind: Literal["metric", "filter"]
    ok: bool
    value: str | None = None  # metric: its value over the table; filter: how many rows it keeps
    problem: str | None = None
