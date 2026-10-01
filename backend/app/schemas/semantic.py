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


class SemanticLayerSchema(CamelModel):
    dataset_id: str
    summary: str = ""
    tables: list[TableSchema]
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    # Whether the descriptions came from the AI or from simple name-based guessing
    generated_by: Literal["heuristic", "llm"] = "heuristic"