"""JSON for query results, shared by the model, the history and the page."""

import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from glint.engine import Result


def result_json(result: Result) -> str:
    rows = [[_jsonable(v) for v in row] for row in result.rows]
    # allow_nan=False: bare NaN and Infinity aren't JSON, and the browser
    # rejects them, so _jsonable must have turned them into strings.
    return json.dumps({"columns": result.columns, "rows": rows}, allow_nan=False)


def _jsonable(value: Any) -> Any:
    """A query value as something json can encode."""
    match value:
        case None | bool() | int() | str():
            return value
        case float() | Decimal() if math.isnan(value):
            return "NaN"
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
