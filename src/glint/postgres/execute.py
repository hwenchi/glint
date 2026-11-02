"""Run validated queries with bounded cost."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import psycopg
from pglast import ast
from pglast.enums import LimitOption
from pglast.stream import RawStream
from psycopg.pq import TransactionStatus

from glint.engine import RawResult, TooManyRows


def run(
    conn: psycopg.Connection,
    stmt: ast.SelectStmt | ast.ExplainStmt,
    max_rows: int,
    timeout: timedelta,
) -> RawResult:
    """Run a validated statement, failing rather than truncating past max_rows."""
    match stmt:
        case ast.ExplainStmt():
            sql = RawStream()(stmt)  # can't be wrapped, and a plan is small
        case ast.SelectStmt():
            sql = with_limit(stmt, max_rows + 1)
    with _transaction(conn, timeout):
        cur = conn.execute(sql)
        rows = cur.fetchall()
        columns = [d.name for d in cur.description]
    if len(rows) > max_rows:
        raise TooManyRows(max_rows)
    return RawResult(columns, rows)


@contextmanager
def _transaction(conn: psycopg.Connection, timeout: timedelta) -> Iterator[None]:
    """A read-only transaction with a statement timeout, always rolled back."""
    if conn.autocommit or conn.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("connection must not be in autocommit or a transaction")
    try:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str(int(timeout.total_seconds() * 1000)),),
        )
        yield
    finally:
        conn.rollback()


def with_limit(stmt: ast.SelectStmt, limit: int) -> str:
    """SQL for the statement wrapped in SELECT * ... LIMIT.

    Generated from the validated tree, not the original text, so what runs is
    exactly what was checked. The planner sees the limit, so ORDER BY keeps only
    the top rows instead of sorting everything.
    """
    wrapped = ast.SelectStmt(
        targetList=(ast.ResTarget(val=ast.ColumnRef(fields=(ast.A_Star(),))),),
        fromClause=(ast.RangeSubselect(subquery=stmt, alias=ast.Alias(aliasname="q")),),
        limitCount=ast.A_Const(val=ast.Integer(ival=limit)),
        limitOption=LimitOption.LIMIT_OPTION_COUNT,
    )
    return RawStream()(wrapped)
