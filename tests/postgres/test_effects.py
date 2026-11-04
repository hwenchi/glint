import pytest
from pglast import parse_sql

from glint.postgres.effects import Cause, Effect, effects


def found(sql):
    """Each effect of the query's parts, with the type of node that causes it, in sorted order."""
    [stmt] = parse_sql(sql)
    [_catalog, _settings, _clock, *parts] = effects(stmt.stmt)
    return sorted((cause.effect, type(cause.node).__name__) for cause in parts)


@pytest.mark.parametrize(
    "sql, expected",
    [
        # Functions
        ("SELECT nextval('s')", [(Effect.WRITES_DATA, "FuncCall"), (Effect.WRITES_SESSION_STATE, "FuncCall")]),
        ("SELECT pg_catalog.nextval('s')", [(Effect.WRITES_DATA, "FuncCall"), (Effect.WRITES_SESSION_STATE, "FuncCall")]),
        ("SELECT lower('A')", []),
        ("SELECT gen_random_uuid()", [(Effect.READS_RANDOM_SOURCE, "FuncCall")]),
        ("SELECT mystery(1)", [(Effect.UNCLASSIFIED, "FuncCall")]),
        ("SELECT public.lower('A')", [(Effect.OPAQUE, "FuncCall")]),
        # Relations
        ("SELECT * FROM film", [(Effect.READS_DATA, "RangeVar")]),
        ("SELECT * FROM public.film", [(Effect.READS_DATA, "RangeVar")]),
        ("SELECT * FROM pg_catalog.pg_class", []),
        ("SELECT * FROM information_schema.tables", []),
        ("SELECT * FROM pg_class", [(Effect.READS_DATA, "RangeVar")]),
        # Keywords
        ("SELECT current_date", []),
        ("SELECT current_timestamp", []),
        ("SELECT current_user", [(Effect.READS_SESSION_STATE, "SQLValueFunction")]),
        ("SELECT current_schema", []),
        # Locking clauses
        ("SELECT 1 FOR UPDATE", [(Effect.WRITES_LOCKS, "LockingClause")]),
        ("SELECT 1 FOR SHARE SKIP LOCKED", [(Effect.READS_LOCKS, "LockingClause"), (Effect.WRITES_LOCKS, "LockingClause")]),
        ("SELECT 1 FOR UPDATE NOWAIT", [(Effect.READS_LOCKS, "LockingClause"), (Effect.WRITES_LOCKS, "LockingClause")]),
        # Types
        ("SELECT 1::int", []),
        ("SELECT 'film'::regclass", []),
        ("SELECT 1::myschema.mytype", [(Effect.OPAQUE, "TypeName")]),
        # Operators
        ("SELECT 1 + 1", []),
        ("SELECT 1 OPERATOR(pg_catalog.+) 1", []),
        ("SELECT 1 OPERATOR(public.+) 1", [(Effect.OPAQUE, "A_Expr")]),
        ("SELECT 1 OPERATOR(public.=) ANY (SELECT 1)", [(Effect.OPAQUE, "SubLink")]),
        ("SELECT 1 ORDER BY 1 USING OPERATOR(public.<)", [(Effect.OPAQUE, "SortBy")]),
        # Nodes with no classification
        ("SELECT * FROM film TABLESAMPLE SYSTEM (1)", [(Effect.READS_DATA, "RangeVar"), (Effect.UNCLASSIFIED, "RangeTableSample")]),
    ],
)
def test_effects(sql, expected):
    assert found(sql) == expected


def test_effects_of_every_query():
    [stmt] = parse_sql("SELECT 1")
    assert list(effects(stmt.stmt)) == [
        Cause(Effect.READS_CATALOG, stmt.stmt),
        Cause(Effect.READS_SESSION_SETTINGS, stmt.stmt),
        Cause(Effect.READS_CLOCK, stmt.stmt),
    ]


def test_effects_of_nested_parts():
    sql = """
        WITH c AS (SELECT nextval('s') AS n)
        SELECT (SELECT currval('s')), n FROM c WHERE n IN (SELECT pg_advisory_lock(1))
    """
    assert found(sql) == [
        (Effect.READS_DATA, "RangeVar"),  # c, the CTE, is read like a relation
        (Effect.READS_SESSION_STATE, "FuncCall"),
        (Effect.WRITES_DATA, "FuncCall"),
        (Effect.WRITES_LOCKS, "FuncCall"),
        (Effect.WRITES_SESSION_STATE, "FuncCall"),
    ]


def test_each_occurrence_is_a_cause():
    assert found("SELECT nextval('s'), nextval('s')") == [
        (Effect.WRITES_DATA, "FuncCall"),
        (Effect.WRITES_DATA, "FuncCall"),
        (Effect.WRITES_SESSION_STATE, "FuncCall"),
        (Effect.WRITES_SESSION_STATE, "FuncCall"),
    ]
