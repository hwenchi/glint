"""Static check that a query is a single read-only SELECT.

Functions and operators are checked by name, so the query must run with
search_path pinned to pg_catalog, pg_temp. Otherwise an unqualified name can
resolve to a user-defined object in another schema.
"""

from pglast import ast, parse_sql
from pglast.enums import A_Expr_Kind
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


class FunctionNotAllowed(Rejected):
    """A function outside the allowlist, or qualified with a schema other than pg_catalog."""

    def __init__(self, name: str):
        super().__init__(f"function {name} is not allowed")
        self.name = name


class OperatorNotAllowed(Rejected):
    """An operator qualified with a schema other than pg_catalog."""

    def __init__(self, name: str):
        super().__init__(f"operator {name} is not allowed")
        self.name = name


class TypeNotAllowed(Rejected):
    """A type qualified with a schema other than pg_catalog."""

    def __init__(self, name: str):
        super().__init__(f"type {name} is not allowed")
        self.name = name


# Built-in functions with no side effects. Functions that make a large value from
# a small input (repeat, lpad, rpad) or concatenate a whole group (array_agg,
# string_agg) are left out, because the timeout doesn't bound memory.
ALLOWED_FUNCTIONS = {
    # aggregates
    "count", "sum", "avg", "min", "max",
    "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop",
    "corr", "covar_pop", "covar_samp",
    "regr_slope", "regr_intercept", "regr_r2", "regr_count",
    "regr_avgx", "regr_avgy", "regr_sxx", "regr_syy", "regr_sxy",
    "percentile_cont", "percentile_disc", "mode",
    "bool_and", "bool_or", "every",
    # window functions
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile",
    "lag", "lead", "first_value", "last_value", "nth_value",
    # math
    "abs", "ceil", "ceiling", "floor", "round", "trunc", "sign", "div", "mod",
    "sqrt", "cbrt", "exp", "ln", "log", "log10", "power", "pi",
    "degrees", "radians", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "width_bucket",
    # strings
    "lower", "upper", "initcap", "length", "char_length", "octet_length",
    "substr", "substring", "btrim", "ltrim", "rtrim", "left", "right",
    "replace", "split_part", "concat", "concat_ws", "position", "strpos",
    "starts_with", "regexp_replace", "regexp_match", "regexp_like",
    # dates and times
    "date_trunc", "date_part", "extract", "date_bin", "age", "timezone",
    "make_date", "make_time", "make_timestamp", "make_interval", "isfinite",
    "justify_days", "justify_hours", "justify_interval",
    "to_char", "to_date", "to_timestamp", "to_number",
}

# Their name is the keyword, not an operator. Postgres rewrites them to >= and <=.
BETWEEN_KINDS = {
    A_Expr_Kind.AEXPR_BETWEEN,
    A_Expr_Kind.AEXPR_NOT_BETWEEN,
    A_Expr_Kind.AEXPR_BETWEEN_SYM,
    A_Expr_Kind.AEXPR_NOT_BETWEEN_SYM,
}

# SIMILAR is left out: it wraps its pattern in a hidden function call.
ALLOWED_EXPR_KINDS = BETWEEN_KINDS | {
    A_Expr_Kind.AEXPR_OP,
    A_Expr_Kind.AEXPR_OP_ANY,
    A_Expr_Kind.AEXPR_OP_ALL,
    A_Expr_Kind.AEXPR_DISTINCT,
    A_Expr_Kind.AEXPR_NOT_DISTINCT,
    A_Expr_Kind.AEXPR_NULLIF,
    A_Expr_Kind.AEXPR_IN,
    A_Expr_Kind.AEXPR_LIKE,
    A_Expr_Kind.AEXPR_ILIKE,
}

# Every node in the tree must be one of these. Anything else is rejected.
ALLOWED_NODES = frozenset({
    ast.SelectStmt,
    ast.WithClause,
    ast.CommonTableExpr,
    ast.ResTarget,
    ast.ColumnRef,
    ast.A_Star,
    ast.A_Const,
    ast.String,
    ast.Integer,
    ast.Float,
    ast.Boolean,
    ast.BoolExpr,
    ast.NullTest,
    ast.BooleanTest,
    ast.SortBy,
    ast.GroupingSet,
    ast.RangeVar,
    ast.RangeSubselect,
    ast.JoinExpr,
    ast.Alias,
    ast.SubLink,
    ast.CaseExpr,
    ast.CaseWhen,
    ast.CoalesceExpr,
    ast.MinMaxExpr,
    ast.RowExpr,
    ast.WindowDef,
    ast.A_Expr,
    ast.FuncCall,
    ast.TypeCast,
    ast.TypeName,
})


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
    if type(node) not in ALLOWED_NODES:
        raise NotAllowed(type(node).__name__)
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
        case ast.FuncCall(funcname=names):
            _check_function(names)
        case ast.A_Expr(kind=kind) if kind not in ALLOWED_EXPR_KINDS:
            raise NotAllowed(kind.name)
        case ast.A_Expr(kind=kind, name=names) if kind not in BETWEEN_KINDS:
            _check_builtin(names, OperatorNotAllowed)
        case ast.SubLink(operName=names) if names:
            _check_builtin(names, OperatorNotAllowed)
        case ast.SortBy(useOp=names) if names:
            _check_builtin(names, OperatorNotAllowed)
        case ast.TypeName(names=names):
            _check_builtin(names, TypeNotAllowed)


def _check_function(names: tuple[ast.String, ...]) -> None:
    match [n.sval for n in names]:
        case [name] | ["pg_catalog", name] if name in ALLOWED_FUNCTIONS:
            return
        case parts:
            raise FunctionNotAllowed(".".join(parts))


def _check_builtin(names: tuple[ast.String, ...], error: type[Rejected]) -> None:
    """Reject a name qualified with a schema other than pg_catalog.

    For operators and types only the schema is checked: the executor pins
    search_path to pg_catalog, where every operator and type is built-in and
    has no side effects.
    """
    match [n.sval for n in names]:
        case [_] | ["pg_catalog", _]:
            return
        case parts:
            raise error(".".join(parts))
