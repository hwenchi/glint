"""The Engine for PostgreSQL."""

from collections.abc import Collection
from datetime import timedelta

import psycopg

from glint.engine import QueryError, RawResult, Timeout
from glint.postgres.checks import check_effects, check_statement, parse
from glint.postgres.effects import Effect
from glint.postgres.execute import run

# SQLSTATE classes for errors caused by the query itself, which the model can
# fix: cardinality violation, data exception, syntax error or access rule violation.
QUERY_ERROR_CLASSES = {"21", "22", "42"}


class PostgresEngine:
    def __init__(self, conn: psycopg.Connection, allow: Collection[Effect], max_rows: int, timeout: timedelta):
        self.conn = conn
        self.allow = allow
        self.max_rows = max_rows
        self.timeout = timeout

    def query(self, sql: str) -> RawResult:
        stmt = parse(sql)
        stmt = check_statement(stmt)
        check_effects(stmt, self.allow)
        try:
            return run(self.conn, stmt, self.max_rows, self.timeout)
        except psycopg.errors.QueryCanceled:
            raise Timeout() from None
        except psycopg.Error as e:
            if e.sqlstate and e.sqlstate[:2] in QUERY_ERROR_CLASSES:
                raise QueryError(e.diag.message_primary) from None
            raise
