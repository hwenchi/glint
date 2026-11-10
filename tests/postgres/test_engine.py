import os
from datetime import timedelta

import psycopg
import pytest

from glint.engine import Engine, QueryError, Timeout, TooManyRows
from glint.postgres.checks import Rejected
from glint.postgres.effects import Effect
from glint.postgres.engine import PostgresEngine

ALLOW = [Effect.READS_DATA, Effect.READS_CATALOG, Effect.READS_SESSION_SETTINGS, Effect.READS_CLOCK]


@pytest.fixture
def engine(conn) -> Engine:
    return PostgresEngine(conn, ALLOW, max_rows=100, timeout=timedelta(seconds=1))


def test_query(engine):
    assert engine.query("SELECT count(*) FROM film").rows == [(1000,)]


def test_introspection(engine):
    result = engine.query(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = 'film' ORDER BY ordinal_position"
    )
    assert ("title",) in result.rows


@pytest.mark.parametrize(
    "sql, error",
    [
        ("DELETE FROM film", Rejected),
        ("SELECT film_id FROM film", TooManyRows),
        ("SELECT count(*) FROM generate_series(1, 1000000000)", Timeout),
    ],
)
def test_errors_for_the_model(engine, sql, error):
    with pytest.raises(error):
        engine.query(sql)


@pytest.mark.parametrize(
    "sql, message",
    [
        ("SELECT nope FROM film", 'column "nope" does not exist'),
        ("SELECT 1 / 0", "division by zero"),
        ("SELECT 'x'::int", 'invalid input syntax for type integer: "x"'),
        ("SELECT (SELECT film_id FROM film)", "more than one row returned by a subquery used as an expression"),
        (
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY length) OVER () FROM film",
            "OVER is not supported for ordered-set aggregate percentile_cont",
        ),
        (f"SELECT concat({', '.join(['1'] * 101)})", "cannot pass more than 100 arguments to a function"),
    ],
)
def test_sql_errors_for_the_model(engine, sql, message):
    with pytest.raises(QueryError) as e:
        engine.query(sql)
    assert str(e.value) == message


def test_connection_errors_propagate(engine, conn):
    with psycopg.connect(os.environ["GLINT_TEST_DATABASE_URL"], autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (conn.info.backend_pid,))
    with pytest.raises(psycopg.OperationalError):
        engine.query("SELECT 1")
