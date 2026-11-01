"""Static check that a query is a single read-only SELECT."""

from pglast import ast, parse_sql
from pglast.parser import ParseError


class Rejected(ValueError):
    """The query is not provably safe. The message is meant for the model."""


class InvalidSyntax(Rejected):
    pass


class StatementCount(Rejected):
    pass


class NotSelect(Rejected):
    pass


class SelectInto(Rejected):
    pass


class LockingClause(Rejected):
    pass


class RecursiveCTE(Rejected):
    pass


class ModifyingCTE(Rejected):
    pass


class CrossDatabase(Rejected):
    pass


class NotAllowed(Rejected):
    """A construct outside the allowlist."""

    def __init__(self, construct: str):
        super().__init__(f"{construct} is not allowed")
        self.construct = construct


def validate(sql: str) -> ast.SelectStmt:
    """Return the parsed statement, or raise Rejected."""
    try:
        stmts = parse_sql(sql)
    except ParseError as e:
        raise InvalidSyntax(f"syntax error: {e}") from None
    if len(stmts) != 1:
        raise StatementCount(f"expected exactly one statement, got {len(stmts)}")
    stmt = stmts[0].stmt
    if not isinstance(stmt, ast.SelectStmt):
        raise NotSelect(f"only SELECT is allowed, got {type(stmt).__name__}")
    _check_tree(stmt)
    return stmt


def _check_tree(root: ast.Node) -> None:
    """Check every node, iteratively since parse trees can be thousands deep."""
    stack = [root]
    while stack:
        value = stack.pop()
        if isinstance(value, (list, tuple)):
            stack.extend(value)
        elif isinstance(value, ast.Node):
            _check_node(value)
            stack.extend(getattr(value, name) for name in value)


def _check_node(node: ast.Node) -> None:
    """Reject the node unless its type is allowed and its fields are safe."""
    match node:
        case ast.SelectStmt(intoClause=into) if into is not None:
            raise SelectInto("SELECT INTO is not allowed")
        case ast.SelectStmt(lockingClause=locks) if locks:
            raise LockingClause("locking clauses (FOR UPDATE, FOR SHARE, ...) are not allowed")
        case ast.WithClause(recursive=True):
            raise RecursiveCTE("WITH RECURSIVE is not allowed")
        case ast.CommonTableExpr(ctequery=query) if not isinstance(query, ast.SelectStmt):
            raise ModifyingCTE(f"CTE {node.ctename} must be a SELECT")
        case ast.RangeVar(catalogname=catalog) if catalog:
            raise CrossDatabase("database-qualified table names are not allowed")
        case (
            ast.SelectStmt()
            | ast.WithClause()
            | ast.CommonTableExpr()
            | ast.ResTarget()
            | ast.ColumnRef()
            | ast.A_Star()
            | ast.A_Const()
            | ast.String()
            | ast.Integer()
            | ast.Float()
            | ast.Boolean()
            | ast.BoolExpr()
            | ast.NullTest()
            | ast.BooleanTest()
            | ast.SortBy()
            | ast.GroupingSet()
            | ast.RangeVar()
            | ast.RangeSubselect()
            | ast.JoinExpr()
            | ast.Alias()
            | ast.SubLink()
            | ast.CaseExpr()
            | ast.CaseWhen()
            | ast.CoalesceExpr()
            | ast.MinMaxExpr()
            | ast.RowExpr()
        ):
            pass
        case _:
            raise NotAllowed(type(node).__name__)
