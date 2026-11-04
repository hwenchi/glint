import pytest
from pglast import ast

from glint.postgres.checks import (
    EffectsNotAllowed,
    InvalidSyntax,
    ModifyingCTE,
    NotSelect,
    Rejected,
    SelectInto,
    StatementCount,
    check_effects,
    check_statement,
    parse,
)
from glint.postgres.effects import Effect

DEEP = "SELECT " + "NOT " * 2000 + "true"  # deeper than Python's default recursion limit
EVERY_QUERY = [Effect.READS_CATALOG, Effect.READS_SESSION_SETTINGS, Effect.READS_CLOCK]


def test_parse():
    assert isinstance(parse("SELECT 1"), ast.SelectStmt)


@pytest.mark.parametrize(
    "sql, error",
    [
        ("SELEC 1", InvalidSyntax),
        ("", StatementCount),
        ("SELECT 1; SELECT 2", StatementCount),
    ],
)
def test_parse_rejects(sql, error):
    with pytest.raises(error):
        parse(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT a FROM t",
        "VALUES (1), (2)",
        "SELECT a FROM t UNION ALL SELECT a FROM u",
        "WITH x AS (SELECT a FROM t) SELECT a FROM x",
        "EXPLAIN ANALYZE SELECT a FROM t",
        DEEP,
    ],
)
def test_check_statement_accepts(sql):
    check_statement(parse(sql))


@pytest.mark.parametrize(
    "sql, error",
    [
        ("DELETE FROM t", NotSelect),
        ("INSERT INTO t VALUES (1)", NotSelect),
        ("CREATE TABLE t (a int)", NotSelect),
        ("SET search_path = public", NotSelect),
        ("EXPLAIN ANALYZE DELETE FROM t", NotSelect),
        ("SELECT a INTO u FROM t", SelectInto),
        ("EXPLAIN SELECT a INTO u FROM t", SelectInto),
        ("WITH x AS (DELETE FROM t RETURNING a) SELECT a FROM x", ModifyingCTE),
        ("SELECT * FROM (WITH x AS (UPDATE t SET a = 1 RETURNING a) SELECT a FROM x) AS s", ModifyingCTE),
    ],
)
def test_check_statement_rejects(sql, error):
    with pytest.raises(error):
        check_statement(parse(sql))


@pytest.mark.parametrize(
    "sql, message",
    [
        ("DELETE FROM t", "Only SELECT is allowed. Found:\nDELETE FROM t"),
        ("EXPLAIN DELETE FROM t", "Only EXPLAIN SELECT is allowed. Found:\nEXPLAIN DELETE FROM t"),
        ("SELECT a INTO u FROM t", "SELECT INTO is not allowed. Found:\nSELECT a INTO u FROM t"),
        (
            "WITH x AS (DELETE FROM t RETURNING a) SELECT a FROM x",
            "Only SELECT is allowed in a CTE. Found:\nx AS (DELETE FROM t RETURNING a)",
        ),
    ],
)
def test_check_statement_message(sql, message):
    with pytest.raises(Rejected) as e:
        check_statement(parse(sql))
    assert str(e.value) == message


@pytest.mark.parametrize(
    "sql, allow",
    [
        ("SELECT 1", EVERY_QUERY),
        ("SELECT now() FROM film", [*EVERY_QUERY, Effect.READS_DATA]),
        (DEEP, EVERY_QUERY),
    ],
)
def test_check_effects_accepts(sql, allow):
    check_effects(parse(sql), allow)


@pytest.mark.parametrize(
    "sql, allow, not_allowed",
    [
        ("SELECT 1", [Effect.READS_SESSION_SETTINGS, Effect.READS_CLOCK], {Effect.READS_CATALOG}),
        ("SELECT 1", [Effect.READS_CATALOG, Effect.READS_CLOCK], {Effect.READS_SESSION_SETTINGS}),
        ("SELECT 1", [Effect.READS_CATALOG, Effect.READS_SESSION_SETTINGS], {Effect.READS_CLOCK}),
        ("SELECT 1 FROM film", EVERY_QUERY, {Effect.READS_DATA}),
        (
            "SELECT nextval('s') FROM film",
            [*EVERY_QUERY, Effect.READS_DATA],
            {Effect.WRITES_DATA, Effect.WRITES_SESSION_STATE},
        ),
    ],
)
def test_check_effects_rejects(sql, allow, not_allowed):
    with pytest.raises(EffectsNotAllowed) as e:
        check_effects(parse(sql), allow)
    assert {cause.effect for cause in e.value.causes} == not_allowed


@pytest.mark.parametrize(
    "sql, cause",
    [
        ("SELECT public.f(1)", "[opaque] public.f(1)"),
        ("SELECT 1 FROM film", "[reads_data] film"),
        ("SELECT 1 OPERATOR(public.+) 2", "[opaque] 1 OPERATOR(public.+) 2"),
        ("SELECT 1::public.t", "[opaque] public.t"),
    ],
)
def test_check_effects_message(sql, cause):
    with pytest.raises(EffectsNotAllowed) as e:
        check_effects(parse(sql), EVERY_QUERY)
    assert str(e.value) == f"The query may have effects that are not allowed. Found:\n{cause}"
