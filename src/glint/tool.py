"""The one tool the model has: run a query, optionally with a chart."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from glint.engine import Engine, QueryError, Result
from glint.serialize import result_json
from glint.spec import UrlNotAllowed, reject_urls

# Description before sql: models write arguments in schema order, so stating
# the intent first works as a plan for the SQL.
QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "query",
        "description": (
            "Run a read-only SQL query and see its result. Every query is shown to"
            " the user as a table; add a Vega-Lite spec to also show it as a chart."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What the query does, in plain language for someone who doesn't read SQL.",
                },
                "sql": {"type": "string", "description": "A single SELECT or EXPLAIN SELECT."},
                "spec": {
                    "type": "object",
                    "description": (
                        "Optional Vega-Lite spec charting the result. Don't include data:"
                        " the query's result becomes the chart's data, replacing any"
                        " top-level data in the spec. Omit for lookups and checks."
                    ),
                },
            },
            "required": ["description", "sql"],
        },
    },
}


class QueryArgs(BaseModel):
    """Parses the query tool's arguments. QUERY_TOOL, written for the model, must match."""

    description: str
    sql: str
    spec: dict[str, Any] | None = None


class InvalidToolCall(Exception):
    """The model's tool call doesn't fit QUERY_TOOL. The message is meant for the model."""


def parse_arguments(name: str, arguments: str) -> QueryArgs:
    if name != QUERY_TOOL["function"]["name"]:
        raise InvalidToolCall(f"unknown tool {name}")
    try:
        return QueryArgs.model_validate_json(arguments)
    except ValidationError as e:
        raise InvalidToolCall(str(e)) from None


@dataclass(frozen=True)
class Call:
    description: str
    sql: str
    spec: dict[str, Any] | None
    at: datetime
    result: Result | None
    error: str | None

    def content(self) -> str:
        """What the model sees: the tool message's content."""
        return f"error: {self.error}" if self.error is not None else result_json(self.result)


def call(engine: Engine, description: str, sql: str, spec: dict[str, Any] | None = None) -> Call:
    at = datetime.now(UTC)
    try:
        if spec is not None:
            spec = {"description": description, **spec}
            reject_urls(spec)
        result = engine.query(sql)
    except (QueryError, UrlNotAllowed) as e:
        return Call(description, sql, spec, at, None, str(e))
    return Call(description, sql, spec, at, result, None)
