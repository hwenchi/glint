from enum import Enum, auto

import pytest
from pglast import ast

from glint.postgres.validate import (
    ALLOWED_NODES,
    CrossDatabase,
    FunctionNotAllowed,
    InvalidSyntax,
    LockingClause,
    ModifyingCTE,
    NotAllowed,
    NotSelect,
    OperatorNotAllowed,
    RecursiveCTE,
    SelectInto,
    StatementCount,
    TypeNotAllowed,
    validate,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT a FROM t",
        "SELECT * FROM s.t AS x",
        "SELECT a FROM t WHERE b IS NULL AND c IS TRUE ORDER BY a LIMIT 10",
        "SELECT a FROM t JOIN u USING (id)",
        "SELECT a FROM t UNION ALL SELECT a FROM u",
        "WITH x AS (SELECT a FROM t) SELECT a FROM x",
        "SELECT a FROM (SELECT a FROM t) AS s",
        "SELECT a FROM t WHERE EXISTS (SELECT 1 FROM u)",
        "SELECT CASE WHEN a IS NULL THEN 0 ELSE 1 END FROM t",
        "SELECT COALESCE(a, b), GREATEST(a, b) FROM t",
        "SELECT a FROM t GROUP BY ROLLUP (a)",
        "VALUES (1), (2)",
        # functions
        "SELECT count(*), avg(a) FROM t",
        "SELECT pg_catalog.count(*) FROM t",
        "SELECT COUNT(*) FROM t",
        "SELECT count(DISTINCT a) FILTER (WHERE b IS NULL) FROM t",
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY a) FROM t",
        "SELECT rank() OVER (PARTITION BY a ORDER BY b) FROM t",
        "SELECT extract(year FROM d), substring(s FROM 2), trim(s) FROM t",
        # operators
        "SELECT a + b * 2, -a, a || 'x' FROM t WHERE a = 1 AND b <> 2",
        "SELECT a FROM t WHERE a != 1",
        "SELECT a FROM t WHERE a OPERATOR(pg_catalog.=) 1",
        "SELECT a FROM t WHERE a = ANY (SELECT b FROM u) AND a < ALL (SELECT b FROM u)",
        "SELECT a FROM t WHERE a IS DISTINCT FROM b AND a IS NOT DISTINCT FROM c",
        "SELECT NULLIF(a, 0) FROM t",
        "SELECT a FROM t WHERE a IN (1, 2) AND b NOT IN (3)",
        "SELECT a FROM t WHERE s LIKE 'x%' AND s NOT ILIKE 'y%' AND s ~ '^z'",
        "SELECT a FROM t WHERE a BETWEEN 1 AND 2 AND b NOT BETWEEN SYMMETRIC 3 AND 1",
        "SELECT j -> 'k', j ->> 'k', a << 2 FROM t WHERE j @> b AND a && b",
        "SELECT a FROM t WHERE a IN (SELECT b FROM u) AND a < ALL (SELECT b FROM u)",
        "SELECT a FROM t ORDER BY a USING <",
        "SELECT a FROM t ORDER BY a USING OPERATOR(pg_catalog.<)",
        # casts
        "SELECT a::int, CAST(b AS varchar(3)), c::numeric(10, 2)[] FROM t",
        "SELECT a::pg_catalog.text, a::regclass FROM t",
        "SELECT a FROM t WHERE d > date '2024-01-01' - interval '1 day'",
        # functions in FROM
        "SELECT a FROM generate_series(1, 10) AS a",
        "SELECT * FROM generate_series(1, 10) WITH ORDINALITY AS a(v, n)",
        "SELECT * FROM ROWS FROM (generate_series(1, 3), unnest(b)) AS a",
        "SELECT * FROM t, LATERAL generate_series(1, t.n) AS a",
        "SELECT " + " + ".join(["1"] * 5000),
    ],
)
def test_accepts(sql):
    validate(sql)


def test_accepts_deep_nesting():
    # Deeper than Python's default recursion limit of 1000.
    validate("SELECT " + "NOT " * 2000 + "true")


@pytest.mark.parametrize(
    "sql, error",
    [
        ("", StatementCount),
        ("SELECT 1; SELECT 2", StatementCount),
        ("SELECT 1; DELETE FROM t", StatementCount),
        ("DELETE FROM t", NotSelect),
        ("INSERT INTO t VALUES (1)", NotSelect),
        ("UPDATE t SET a = 1", NotSelect),
        ("CREATE TABLE t (a int)", NotSelect),
        ("SET search_path = public", NotSelect),
        ("COPY t TO '/tmp/x'", NotSelect),
        ("EXPLAIN ANALYZE DELETE FROM t", NotSelect),
        ("SELEC 1", InvalidSyntax),
        # writes and locks hidden inside a SELECT
        ("SELECT a INTO u FROM t", SelectInto),
        ("SELECT a FROM t FOR UPDATE", LockingClause),
        ("SELECT a FROM t FOR SHARE", LockingClause),
        ("SELECT a FROM (SELECT a FROM t FOR UPDATE) AS s", LockingClause),
        ("WITH x AS (DELETE FROM t RETURNING a) SELECT a FROM x", ModifyingCTE),
        ("WITH x AS (INSERT INTO t VALUES (1) RETURNING a) SELECT a FROM x", ModifyingCTE),
        ("WITH x AS (UPDATE t SET a = 1 RETURNING a) SELECT a FROM x", ModifyingCTE),
        # unbounded or outside the database
        ("WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT 1 FROM x) SELECT 1 FROM x", RecursiveCTE),
        ("SELECT a FROM otherdb.s.t", CrossDatabase),
    ],
)
def test_rejects(sql, error):
    with pytest.raises(error):
        validate(sql)


@pytest.mark.parametrize(
    "sql, construct",
    [
        ("SELECT a FROM t TABLESAMPLE BERNOULLI (1)", "RangeTableSample"),
        ("SELECT a FROM XMLTABLE('/a' PASSING '<a/>' COLUMNS a int)", "RangeTableFunc"),
        ("SELECT $1", "ParamRef"),
        ("SELECT a FROM t WHERE s SIMILAR TO 'x%'", "AEXPR_SIMILAR"),
        ("SELECT * FROM unnest(b) AS x(a int)", "ColumnDef"),
    ],
)
def test_not_allowed(sql, construct):
    with pytest.raises(NotAllowed) as e:
        validate(sql)
    assert e.value.construct == construct


@pytest.mark.parametrize(
    "sql, name",
    [
        # side effects or outside the database
        ("SELECT pg_sleep(10)", "pg_sleep"),
        ("SELECT nextval('s')", "nextval"),
        ("SELECT set_config('search_path', 'public', false)", "set_config"),
        ("SELECT pg_advisory_lock(1)", "pg_advisory_lock"),
        ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
        ("SELECT lo_export(1, '/tmp/x')", "lo_export"),
        ("SELECT dblink('host=x', 'DELETE FROM t')", "dblink"),
        # large values from small inputs
        ("SELECT repeat('x', 1000000000)", "repeat"),
        ("SELECT string_agg(a, ',') FROM t", "string_agg"),
        # shadowing a built-in from another schema
        ("SELECT public.count(*) FROM t", "public.count"),
        ("SELECT db.pg_catalog.count(*) FROM t", "db.pg_catalog.count"),
        ('SELECT "COUNT"(*) FROM t', "COUNT"),
        # nested inside an allowed function
        ("SELECT count(pg_sleep(1)) FROM t", "pg_sleep"),
        # in FROM
        ("SELECT * FROM pg_sleep(10)", "pg_sleep"),
        ("SELECT * FROM public.f() AS x", "public.f"),
        ("SELECT * FROM ROWS FROM (generate_series(1, 3), pg_sleep(10)) AS a", "pg_sleep"),
        ("SELECT * FROM generate_series(1, pg_sleep(1)::int) AS a", "pg_sleep"),
    ],
)
def test_function_not_allowed(sql, name):
    with pytest.raises(FunctionNotAllowed) as e:
        validate(sql)
    assert e.value.name == name


@pytest.mark.parametrize(
    "sql, name",
    [
        ("SELECT a FROM t WHERE a OPERATOR(public.=) 1", "public.="),
        ("SELECT a FROM t WHERE a OPERATOR(public.@>) ANY (SELECT b FROM u)", "public.@>"),
        ("SELECT a FROM t WHERE a OPERATOR(public.<) ALL (SELECT b FROM u)", "public.<"),
        # nested inside allowed constructs
        ("SELECT count(*) FILTER (WHERE a OPERATOR(public.=) b) FROM t", "public.="),
        ("SELECT a FROM t WHERE a IN (b OPERATOR(public.+) c)", "public.+"),
        # ORDER BY ... USING, wherever ORDER BY appears
        ("SELECT a FROM t ORDER BY a USING OPERATOR(public.<)", "public.<"),
        ("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY a USING OPERATOR(public.<)) FROM t", "public.<"),
        ("SELECT rank() OVER (ORDER BY a USING OPERATOR(public.<)) FROM t", "public.<"),
    ],
)
def test_operator_not_allowed(sql, name):
    with pytest.raises(OperatorNotAllowed) as e:
        validate(sql)
    assert e.value.name == name


@pytest.mark.parametrize(
    "sql, name",
    [
        ("SELECT a::public.mytype FROM t", "public.mytype"),
        ("SELECT CAST(a AS public.mytype) FROM t", "public.mytype"),
        ("SELECT public.mytype 'x'", "public.mytype"),
        ("SELECT a::db.pg_catalog.int4 FROM t", "db.pg_catalog.int4"),
        # nested inside allowed constructs
        ("SELECT count(a::public.mytype) FROM t", "public.mytype"),
        ("SELECT a FROM t WHERE a IN (b::public.mytype)", "public.mytype"),
    ],
)
def test_type_not_allowed(sql, name):
    with pytest.raises(TypeNotAllowed) as e:
        validate(sql)
    assert e.value.name == name


class Field(Enum):
    """What a list or string field of a node holds."""

    OPERATOR = auto()  # resolved to code: checked by the validator
    FUNCTION = auto()  # resolved to code: checked by the validator
    TYPE = auto()  # resolved to code: checked by the validator
    TABLE = auto()  # checked against the catalog
    REJECTED = auto()  # the validator rejects the node if set
    COLUMN = auto()
    LOCAL_NAME = auto()  # alias, CTE, window or output column name
    LITERAL = auto()
    ANALYSIS = auto()  # filled by parse analysis, empty in a raw parse tree
    NODES = auto()  # child nodes, each checked by the walker


REVIEWED_FIELDS = {
    (ast.A_Expr, "name"): Field.OPERATOR,
    (ast.SubLink, "operName"): Field.OPERATOR,
    (ast.SortBy, "useOp"): Field.OPERATOR,
    (ast.FuncCall, "funcname"): Field.FUNCTION,
    (ast.TypeName, "names"): Field.TYPE,
    (ast.TypeName, "typmods"): Field.NODES,
    (ast.TypeName, "arrayBounds"): Field.NODES,
    (ast.RangeVar, "schemaname"): Field.TABLE,
    (ast.RangeVar, "relname"): Field.TABLE,
    (ast.RangeVar, "catalogname"): Field.REJECTED,
    (ast.SelectStmt, "lockingClause"): Field.REJECTED,
    (ast.ColumnRef, "fields"): Field.COLUMN,
    (ast.JoinExpr, "usingClause"): Field.COLUMN,
    (ast.Alias, "aliasname"): Field.LOCAL_NAME,
    (ast.Alias, "colnames"): Field.LOCAL_NAME,
    (ast.CommonTableExpr, "ctename"): Field.LOCAL_NAME,
    (ast.CommonTableExpr, "aliascolnames"): Field.LOCAL_NAME,
    (ast.ResTarget, "name"): Field.LOCAL_NAME,
    (ast.RowExpr, "colnames"): Field.LOCAL_NAME,
    (ast.WindowDef, "name"): Field.LOCAL_NAME,
    (ast.WindowDef, "refname"): Field.LOCAL_NAME,
    (ast.String, "sval"): Field.LITERAL,
    (ast.Float, "fval"): Field.LITERAL,
    (ast.CommonTableExpr, "ctecolnames"): Field.ANALYSIS,
    (ast.CommonTableExpr, "ctecoltypes"): Field.ANALYSIS,
    (ast.CommonTableExpr, "ctecoltypmods"): Field.ANALYSIS,
    (ast.CommonTableExpr, "ctecolcollations"): Field.ANALYSIS,
    (ast.BoolExpr, "args"): Field.NODES,
    (ast.CaseExpr, "args"): Field.NODES,
    (ast.CoalesceExpr, "args"): Field.NODES,
    (ast.FuncCall, "args"): Field.NODES,
    (ast.FuncCall, "agg_order"): Field.NODES,
    (ast.RangeFunction, "functions"): Field.NODES,
    (ast.RangeFunction, "coldeflist"): Field.NODES,
    (ast.GroupingSet, "content"): Field.NODES,
    (ast.MinMaxExpr, "args"): Field.NODES,
    (ast.ResTarget, "indirection"): Field.NODES,
    (ast.RowExpr, "args"): Field.NODES,
    (ast.SelectStmt, "distinctClause"): Field.NODES,
    (ast.SelectStmt, "targetList"): Field.NODES,
    (ast.SelectStmt, "fromClause"): Field.NODES,
    (ast.SelectStmt, "groupClause"): Field.NODES,
    (ast.SelectStmt, "windowClause"): Field.NODES,
    (ast.SelectStmt, "valuesLists"): Field.NODES,
    (ast.SelectStmt, "sortClause"): Field.NODES,
    (ast.WindowDef, "partitionClause"): Field.NODES,
    (ast.WindowDef, "orderClause"): Field.NODES,
    (ast.WithClause, "ctes"): Field.NODES,
}


def test_fields_reviewed():
    """Fails when an allowed node has a list or string field not reviewed above.

    That happens after adding a node type to ALLOWED_NODES or upgrading pglast.
    Decide what the new field holds, check it in the validator if Postgres
    resolves it to code, and add it to REVIEWED_FIELDS.
    """
    fields = {
        (cls, name)
        for cls in ALLOWED_NODES
        for name, info in cls.__slots__.items()
        if info.c_type in ("List*", "char*")
    }
    assert fields == REVIEWED_FIELDS.keys()
