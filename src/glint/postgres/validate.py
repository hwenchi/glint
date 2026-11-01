"""Static check that a query is a single read-only SELECT."""

from pglast import ast, parse_sql
from pglast.parser import ParseError


class Rejected(ValueError):
    """The query is not provably safe. The message is meant for the model."""


def validate(sql: str) -> ast.SelectStmt:
    """Return the parsed statement, or raise Rejected."""
    try:
        stmts = parse_sql(sql)
    except ParseError as e:
        raise Rejected(f"syntax error: {e}") from None
    if len(stmts) != 1:
        raise Rejected(f"expected exactly one statement, got {len(stmts)}")
    stmt = stmts[0].stmt
    if not isinstance(stmt, ast.SelectStmt):
        raise Rejected(f"only SELECT is allowed, got {type(stmt).__name__}")
    return stmt
