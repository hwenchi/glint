"""Traversal of pglast parse trees."""

from collections.abc import Iterator

from pglast import ast


def walk(root: ast.Node) -> Iterator[ast.Node]:
    """Yield every node in the tree, iteratively since trees can be thousands deep."""
    stack = [root]
    while stack:
        value = stack.pop()
        if isinstance(value, (list, tuple)):
            stack.extend(value)
        elif isinstance(value, ast.Node):
            yield value
            stack.extend(getattr(value, name) for name in value)
