"""The model's tools: run a query, optionally with a chart, and revise its beliefs."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from glint.engine import Engine, QueryError
from glint.serialize import Result
from glint.spec import InvalidSpec, UrlNotAllowed, reject_invalid, reject_urls

# Description before sql: models write arguments in schema order, so stating
# the intent first works as a plan for the SQL.
QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "query",
        "description": (
            "Run SQL and see its result. Every query is shown to"
            " the user as a table; add a Vega-Lite spec to also show it as a chart."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A caption for the result, in plain language for someone who doesn't"
                        " read SQL: what it shows, not an instruction. For example"
                        " \"Average payments per month, across all years\", not"
                        " \"Show the seasonal pattern by comparing months\"."
                    ),
                },
                "sql": {"type": "string", "description": "One SQL statement."},
                "spec": {
                    "type": "object",
                    "description": (
                        "Optional Vega-Lite spec charting the result. Don't include data:"
                        " the query's result becomes the chart's data, replacing any"
                        " top-level data in the spec. Fields must be the result's column"
                        " names. Omit for lookups and checks. Marks: line, point, area, rect,"
                        " boxplot, bar, arc, tick. Example:"
                        ' {"mark": "line", "encoding": {'
                        '"x": {"field": "month", "type": "temporal"},'
                        ' "y": {"field": "total", "type": "quantitative", "title": "Total payments"}}}'
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
    """The model's tool call doesn't fit the tool's definition. The message is meant for the model."""


def parse_arguments(name: str, arguments: str) -> QueryArgs:
    if name != QUERY_TOOL["function"]["name"]:
        raise InvalidToolCall(f"Unknown tool: {name}.")
    try:
        return QueryArgs.model_validate_json(arguments)
    except ValidationError as e:
        raise InvalidToolCall(str(e)) from None


REVISE_BELIEFS_TOOL = {
    "type": "function",
    "function": {
        "name": "revise_beliefs",
        "description": (
            "Revise your beliefs: drop the ones you no longer hold, by number, and add new ones."
            " Either list may be empty."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drop": {"type": "array", "items": {"type": "integer"}, "description": "Numbers of the beliefs to drop."},
                "add": {"type": "array", "items": {"type": "string"}, "description": "New beliefs, one statement each."},
            },
            "required": ["drop", "add"],
            "additionalProperties": False,
        },
    },
}


class ReviseBeliefsArgs(BaseModel):
    """Parses the revise_beliefs tool's arguments, exactly as REVISE_BELIEFS_TOOL gives them: no conversions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    drop: list[int]
    add: list[str]


def parse_revise_beliefs_arguments(name: str, arguments: str) -> ReviseBeliefsArgs:
    if name != REVISE_BELIEFS_TOOL["function"]["name"]:
        raise InvalidToolCall(f"Unknown tool: {name}.")
    try:
        return ReviseBeliefsArgs.model_validate_json(arguments)
    except ValidationError as e:
        raise InvalidToolCall(str(e)) from None


class QueryRun(BaseModel):
    """One attempt to run a query: what was asked, when, and its result or error."""

    model_config = ConfigDict(frozen=True)

    description: str
    sql: str
    spec: dict[str, Any] | None
    at: datetime
    result: Result | None
    error: str | None


def run_query(
    engine: Engine, description: str, sql: str, spec: dict[str, Any] | None = None
) -> QueryRun:
    at = datetime.now(UTC)
    try:
        if spec is not None:
            spec = {"description": description, **spec}
            reject_urls(spec)
            reject_invalid(spec)
        result = Result.from_raw(engine.query(sql))
    except (QueryError, UrlNotAllowed, InvalidSpec) as e:
        return QueryRun(description=description, sql=sql, spec=spec, at=at, result=None, error=str(e))
    return QueryRun(description=description, sql=sql, spec=spec, at=at, result=result, error=None)
