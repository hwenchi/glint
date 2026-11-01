from datetime import timedelta

import psycopg
import pytest
from psycopg.pq import TransactionStatus

from glint.postgres.execute import TooManyRows, _transaction, run, with_limit
from glint.postgres.validate import validate


def test_with_limit():
    sql = with_limit(validate("SELECT a FROM t ORDER BY a"), 1001)
    assert sql == "SELECT * FROM (SELECT a FROM t ORDER BY a) AS q LIMIT 1001"


def test_with_limit_drops_comments():
    sql = with_limit(validate("SELECT 'x)' -- comment"), 10)
    assert sql == "SELECT * FROM (SELECT 'x)') AS q LIMIT 10"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT a FROM t UNION SELECT b FROM u LIMIT 5",
        "WITH x AS (SELECT a FROM t) SELECT a FROM x",
        "SELECT a FROM t ORDER BY a FETCH FIRST 5 ROWS WITH TIES",
        "SELECT rank() OVER (ORDER BY a) FROM t",
        "VALUES (1), (2)",
    ],
)
def test_with_limit_validates(sql):
    # The executor only runs SQL that passes the validator.
    validate(with_limit(validate(sql), 10))


TIMEOUT = timedelta(seconds=5)


def test_run(conn):
    result = run(conn, validate("SELECT rating, count(*) AS n FROM film GROUP BY rating"), 10, TIMEOUT)
    assert result.columns == ["rating", "n"]
    assert sum(n for _, n in result.rows) == 1000


def test_run_at_max_rows(conn):
    assert len(run(conn, validate("SELECT film_id FROM film"), 1000, TIMEOUT).rows) == 1000


def test_run_fails_past_max_rows(conn):
    with pytest.raises(TooManyRows):
        run(conn, validate("SELECT film_id FROM film"), 999, TIMEOUT)


def test_run_times_out(conn):
    stmt = validate("SELECT count(*) FROM generate_series(1, 1000000000)")
    with pytest.raises(psycopg.errors.QueryCanceled):
        run(conn, stmt, 10, timedelta(milliseconds=100))


def test_run_leaves_connection_idle(conn):
    run(conn, validate("SELECT 1"), 10, TIMEOUT)
    assert conn.info.transaction_status == TransactionStatus.IDLE
    with pytest.raises(TooManyRows):
        run(conn, validate("SELECT film_id FROM film"), 1, TIMEOUT)
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_transaction_is_read_only(conn):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with _transaction(conn, TIMEOUT):
            conn.execute("CREATE TABLE should_not_exist ()")


def test_transaction_rolls_back(conn):
    # A session-level setting survives a commit but not a rollback.
    with _transaction(conn, TIMEOUT):
        conn.execute("SELECT set_config('glint.marker', 'set', false)")
    assert conn.execute("SELECT current_setting('glint.marker', true)").fetchone() != ("set",)


def test_transaction_requires_idle_connection(conn):
    conn.execute("SELECT 1")  # opens a transaction
    with pytest.raises(ValueError):
        with _transaction(conn, TIMEOUT):
            pass
