"""The Engine for PostgreSQL."""

from datetime import timedelta

import psycopg

from glint.engine import QueryError, RawResult, Timeout
from glint.postgres.execute import run
from glint.postgres.validate import validate

# SQLSTATE classes for errors caused by the query itself, which the model can
# fix: cardinality violation, data exception, syntax error or access rule violation.
QUERY_ERROR_CLASSES = {"21", "22", "42"}


class PostgresEngine:
    def __init__(self, conn: psycopg.Connection, max_rows: int, timeout: timedelta):
        self.conn = conn
        self.max_rows = max_rows
        self.timeout = timeout

    def query(self, sql: str) -> RawResult:
        stmt = validate(sql)
        try:
            return run(self.conn, stmt, self.max_rows, self.timeout)
        except psycopg.errors.QueryCanceled:
            raise Timeout() from None
        except psycopg.Error as e:
            if e.sqlstate and e.sqlstate[:2] in QUERY_ERROR_CLASSES:
                raise QueryError(e.diag.message_primary) from None
            raise
