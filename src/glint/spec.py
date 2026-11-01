"""Checks on the model's Vega-Lite specs.

Whether a spec renders well is the model's problem. This only rejects URLs,
because they make the browser send network requests, which can carry data out.
The renderer's loader refuses every URL anyway, so this exists to give the
model a clear error.
"""

from typing import Any

# In Vega-Lite, every network request comes from one of these: url for data
# and image marks, href for links.
URL_KEYS = {"url", "href"}


class UrlNotAllowed(Exception):
    """The spec has a URL. The message is meant for the model."""


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
