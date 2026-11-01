import pytest

from glint.postgres.resolve import Table, tables
from glint.postgres.validate import validate


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT 1", set()),
        ("SELECT a FROM t", {Table(None, "t")}),
        ("SELECT a FROM s.t", {Table("s", "t")}),
        ("SELECT a FROM t, s.t", {Table(None, "t"), Table("s", "t")}),
        ("SELECT a FROM t JOIN t AS u ON true", {Table(None, "t")}),
        ("SELECT a FROM t JOIN u USING (id)", {Table(None, "t"), Table(None, "u")}),
        ("SELECT a FROM t UNION SELECT a FROM u", {Table(None, "t"), Table(None, "u")}),
        ("SELECT a FROM (SELECT a FROM t) AS s", {Table(None, "t")}),
        ("SELECT a FROM t WHERE a IN (SELECT a FROM u)", {Table(None, "t"), Table(None, "u")}),
        ("SELECT (SELECT max(a) FROM u) FROM t", {Table(None, "t"), Table(None, "u")}),
        ("SELECT * FROM t, LATERAL generate_series(1, t.n) AS g", {Table(None, "t")}),
        # CTE names are included: the resolver looks them up like any table
        ("WITH x AS (SELECT a FROM t) SELECT a FROM x", {Table(None, "t"), Table(None, "x")}),
        ("WITH t AS (SELECT a FROM t) SELECT a FROM t", {Table(None, "t")}),
        ("SELECT * FROM (WITH v AS (SELECT 1) SELECT * FROM v) s, v", {Table(None, "v")}),
    ],
)
def test_tables(sql, expected):
    assert tables(validate(sql)) == expected
