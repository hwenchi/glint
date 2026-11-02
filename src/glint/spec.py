"""Checks on the model's Vega-Lite specs.

reject_urls keeps charts from sending data out: URLs make the browser send
network requests. The renderer's loader refuses them too; this gives the model
a clear error.

reject_invalid tells the model when Vega-Lite can't read its spec, so it can
fix it.
"""

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import best_match

# In Vega-Lite, every network request comes from one of these: url for data
# and image marks, href for links.
URL_KEYS = {"url", "href"}

# The schema of the Vega-Lite version the page renders with; see make schema.
VALIDATOR = Draft7Validator(json.loads((files("glint") / "schemas" / "vega-lite.json").read_text()))


class UrlNotAllowed(Exception):
    """The spec has a URL. The message is meant for the model."""


class InvalidSpec(Exception):
    """The spec isn't valid Vega-Lite. The message is meant for the model."""


def reject_urls(spec: dict[str, Any]) -> None:
    """Raise UrlNotAllowed if the spec has a url or href key at any depth."""
    stack: list[tuple[str, Any]] = [("$", spec)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key in URL_KEYS:
                    raise UrlNotAllowed(
                        f"{child_path}: URLs are not allowed, charts can't make network requests"
                    )
                stack.append((child_path, child))
        elif isinstance(value, list):
            stack.extend((f"{path}[{i}]", item) for i, item in enumerate(value))


def reject_invalid(spec: dict[str, Any]) -> None:
    """Raise InvalidSpec if the spec isn't valid Vega-Lite."""
    # The query's result becomes the data, so a placeholder stands in for it.
    error = best_match(VALIDATOR.iter_errors({**spec, "data": {"name": "result"}}))
    if error is not None:
        raise InvalidSpec(f"{error.json_path}: {error.message}")
