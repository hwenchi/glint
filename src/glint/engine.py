"""The interface between the agent and a database."""

from typing import Any, NamedTuple, Protocol


class Result(NamedTuple):
    columns: list[str]
    rows: list[tuple[Any, ...]]


class QueryError(Exception):
    """A query the engine won't run or couldn't finish. The message is meant for the model."""


class TooManyRows(QueryError):
    def __init__(self, max_rows: int):
        super().__init__(
            f"the query returned more than {max_rows} rows: aggregate or filter it"
        )
        self.max_rows = max_rows


class Timeout(QueryError):
    def __init__(self):
        super().__init__(
            "the query took too long and was cancelled: "
            "check its cost with EXPLAIN, then filter or aggregate earlier"
        )


class Engine(Protocol):
    def query(self, sql: str) -> Result:
        """Run a read-only query within the engine's limits, or raise QueryError."""
        ...
