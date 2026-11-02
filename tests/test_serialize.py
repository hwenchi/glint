import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from glint.engine import Result
from glint.serialize import result_data


def _reject_constant(name):
    raise ValueError(f"not strict JSON: {name}")


def parse(result):
    """Parse as strictly as a browser's JSON.parse, which rejects NaN and Infinity."""
    return json.loads(result_data(result).model_dump_json(), parse_constant=_reject_constant)


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        (True, True),
        (1, 1),
        ("", ""),
        (1.5, 1.5),
        (Decimal("4.99"), 4.99),
        (datetime(2022, 5, 24, 22, 53, 30, tzinfo=timezone.utc), "2022-05-24T22:53:30+00:00"),
        (date(2022, 5, 24), "2022-05-24"),
        (time(22, 53), "22:53:00"),
        (timedelta(days=3), "3 days, 0:00:00"),
        (UUID("12345678-1234-5678-1234-567812345678"), "12345678-1234-5678-1234-567812345678"),
        ({"k": [1, Decimal("2.5")]}, {"k": [1, 2.5]}),
        ([date(2022, 1, 1), None], ["2022-01-01", None]),
        # NaN and Infinity aren't JSON, so they become strings
        (float("nan"), "NaN"),
        (float("inf"), "Infinity"),
        (float("-inf"), "-Infinity"),
        (Decimal("NaN"), "NaN"),
        (Decimal("-Infinity"), "-Infinity"),
        ([1.0, float("nan")], [1.0, "NaN"]),
    ],
)
def test_value(value, expected):
    assert parse(Result(["x"], [(value,)])) == {"columns": ["x"], "rows": [[expected]]}


def test_empty_result_keeps_columns():
    assert parse(Result(["a", "b"], [])) == {"columns": ["a", "b"], "rows": []}
