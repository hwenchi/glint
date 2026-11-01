import pytest

from glint.postgres.validate import (
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
        # not yet allowed: casts, functions in FROM
        ("SELECT a::int FROM t", "TypeCast"),
        ("SELECT a FROM generate_series(1, 10) AS a", "RangeFunction"),
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
