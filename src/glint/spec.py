"""Validate the model's Vega-Lite specs and combine them with query results."""

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import best_match

from glint.engine import Result

SCHEMA = "vega-lite-v6.5.0.json"
VALIDATOR = Draft7Validator(json.loads((files("glint") / "schemas" / SCHEMA).read_text()))


class InvalidSpec(Exception):
    """The model's spec can't be rendered. The message is meant for the model."""


def snapshot(spec: dict[str, Any], result: Result) -> dict[str, Any]:
    """The spec with the query result as its data, ready to render."""
    # Validate with a placeholder data source, so error messages, which quote
    # the invalid value, never include the result's rows.
    error = best_match(VALIDATOR.iter_errors({**spec, "data": {"name": "result"}}))
    if error is not None:
        raise InvalidSpec(f"{error.json_path}: {error.message}")
    values = [dict(zip(result.columns, row)) for row in result.rows]
    return {**spec, "data": {"values": values}}
