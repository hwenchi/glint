"""Query results as JSON, shared by the model, the history and the page."""

import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from glint.engine import Result


class ResultData(BaseModel):
    """A query result whose values are plain JSON."""

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    rows: list[list[Any]]


def result_data(result: Result) -> ResultData:
    return ResultData(columns=result.columns, rows=[[_jsonable(v) for v in row] for row in result.rows])


def _jsonable(value: Any) -> Any:
    """A query value as plain JSON."""
    match value:
        case None | bool() | int() | str():
            return value
        case float() | Decimal() if math.isnan(value):
            return "NaN"  # NaN and Infinity aren't JSON, and the browser rejects them
        case float() | Decimal() if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        case float() | Decimal():
            return float(value)  # charts need numbers; strings sort as text
        case datetime() | date() | time():
            return value.isoformat()
        case list() | tuple():
            return [_jsonable(v) for v in value]
        case dict():
            return {k: _jsonable(v) for k, v in value.items()}
        case _:
            return str(value)
