import pytest

from glint.postgres.validate import Rejected, validate


def test_accepts_select():
    validate("SELECT a FROM t")


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "SELECT 1; SELECT 2",
        "SELECT 1; DELETE FROM t",
        "DELETE FROM t",
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "CREATE TABLE t (a int)",
        "SET search_path = public",
        "COPY t TO '/tmp/x'",
        "EXPLAIN ANALYZE DELETE FROM t",
        "SELEC 1",
    ],
)
def test_rejects(sql):
    with pytest.raises(Rejected):
        validate(sql)
