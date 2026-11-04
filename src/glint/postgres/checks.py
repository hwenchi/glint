"""The checks a query passes before it runs.

The statement check looks at the statement as a whole: it must be a SELECT, or
EXPLAIN of one, that writes nothing at its top level. The effect check looks at
its parts: each effect any of them may have must be allowed.
"""

from collections.abc import Collection

from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.stream import RawStream

from glint.engine import QueryError
from glint.postgres.effects import Cause, Effect, effects
from glint.postgres.tree import walk


class Rejected(QueryError):
    """The query fails a check."""


class InvalidSyntax(Rejected):
    pass


class StatementCount(Rejected):
    pass


class NotSelect(Rejected):
    pass


class SelectInto(Rejected):
    pass


class ModifyingCTE(Rejected):
    pass


def parse(sql: str) -> ast.Node:
    """The one statement in the text."""
    try:
        stmts = parse_sql(sql)
    except ParseError as e:
        raise InvalidSyntax(f"syntax error: {e}") from None
    if len(stmts) != 1:
        raise StatementCount(f"expected exactly one statement, got {len(stmts)}")
    return stmts[0].stmt


def check_statement(stmt: ast.Node) -> ast.SelectStmt | ast.ExplainStmt:
    """The statement, if it is a SELECT or EXPLAIN SELECT that writes nothing at its top level."""
    match stmt:
        case ast.SelectStmt() | ast.ExplainStmt(query=ast.SelectStmt()):
            pass
        case ast.ExplainStmt(query=query):
            raise NotSelect(f"only EXPLAIN SELECT is allowed, got EXPLAIN {type(query).__name__}")
        case _:
            raise NotSelect(f"only SELECT is allowed, got {type(stmt).__name__}")
    # Postgres allows these only at the top level, but the parser accepts some nested forms.
    for node in walk(stmt):
        match node:
            case ast.SelectStmt(intoClause=into) if into is not None:
                raise SelectInto("SELECT INTO is not allowed")
            case ast.CommonTableExpr(ctequery=query) if not isinstance(query, ast.SelectStmt):
                raise ModifyingCTE(f"CTE {node.ctename} must be a SELECT")
    return stmt


class EffectsNotAllowed(Rejected):
    def __init__(self, causes: list[Cause]):
        lines = "".join(f"\n{cause.effect}: {RawStream()(cause.node)}" for cause in causes)
        super().__init__(f"the query may have effects that are not allowed:{lines}")
        self.causes = causes


def check_effects(stmt: ast.Node, allow: Collection[Effect]) -> None:
    """Reject the statement if it may have an effect not in allow."""
    not_allowed = [cause for cause in effects(stmt) if cause.effect not in allow]
    if not_allowed:
        raise EffectsNotAllowed(not_allowed)
