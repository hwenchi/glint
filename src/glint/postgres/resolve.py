"""Check the tables a validated query reads against the database catalog.

CTE names need no special handling. A reference is looked up as a relation
whether or not it names a CTE: if it resolves, the relation is checked, which
is harmless when the reference meant the CTE; if it doesn't, Postgres resolves
it to the CTE or fails with "relation does not exist".
"""

from typing import NamedTuple

from pglast import ast

from glint.postgres.tree import walk


class Table(NamedTuple):
    schema: str | None
    name: str


def tables(stmt: ast.SelectStmt) -> frozenset[Table]:
    """Every table reference in the query, including ones that may name a CTE."""
    return frozenset(
        Table(node.schemaname, node.relname)
        for node in walk(stmt)
        if isinstance(node, ast.RangeVar)
    )
