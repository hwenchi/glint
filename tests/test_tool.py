import json

import pytest

from glint.engine import QueryError, Result
from glint.tool import QUERY_TOOL, InvalidToolCall, QueryArgs, call, parse_arguments

RESULT = Result(["rating", "n"], [("G", 178)])


class FakeEngine:
    def __init__(self, result=RESULT, error=None):
        self.result = result
        self.error = error
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if self.error:
            raise self.error
        return self.result


def test_call():
    engine = FakeEngine()
    c = call(engine, "Films per rating", "SELECT rating, count(*) AS n FROM film GROUP BY rating")
    assert engine.queries == ["SELECT rating, count(*) AS n FROM film GROUP BY rating"]
    assert (c.result, c.error, c.spec) == (RESULT, None, None)
    assert json.loads(c.content()) == {"columns": ["rating", "n"], "rows": [["G", 178]]}


def test_call_with_spec_gets_description():
    spec = {"mark": "bar"}
    c = call(FakeEngine(), "Films per rating", "SELECT 1", spec)
    assert c.spec == {"description": "Films per rating", "mark": "bar"}
    assert spec == {"mark": "bar"}


def test_call_keeps_spec_description():
    c = call(FakeEngine(), "Films per rating", "SELECT 1", {"description": "Own", "mark": "bar"})
    assert c.spec["description"] == "Own"


def test_url_fails_the_call_without_querying():
    engine = FakeEngine()
    c = call(engine, "Films", "SELECT 1", {"mark": "bar", "encoding": {"href": {"field": "x"}}})
    assert engine.queries == []
    assert c.result is None
    assert c.content().startswith("error: $.encoding.href:")


def test_query_error():
    c = call(FakeEngine(error=QueryError('column "nope" does not exist')), "Films", "SELECT nope")
    assert c.result is None
    assert c.content() == 'error: column "nope" does not exist'


def test_tool_matches_args():
    # QUERY_TOOL is written for the model and QueryArgs parses its calls.
    parameters = QUERY_TOOL["function"]["parameters"]
    assert list(parameters["properties"]) == list(QueryArgs.model_fields)
    assert parameters["required"] == [n for n, f in QueryArgs.model_fields.items() if f.is_required()]


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ('{"description": "d", "sql": "s"}', QueryArgs(description="d", sql="s")),
        ('{"description": "d", "sql": "s", "spec": null}', QueryArgs(description="d", sql="s")),
        ('{"description": "d", "sql": "s", "spec": {"mark": "bar"}}', QueryArgs(description="d", sql="s", spec={"mark": "bar"})),
    ],
)
def test_parse_arguments(arguments, expected):
    assert parse_arguments("query", arguments) == expected


def test_parse_arguments_unknown_tool():
    with pytest.raises(InvalidToolCall) as e:
        parse_arguments("execute", '{"description": "d", "sql": "s"}')
    assert str(e.value) == "unknown tool execute"


@pytest.mark.parametrize(
    "arguments",
    [
        "not json",
        "[]",
        '{"description": "d"}',
        '{"description": "d", "sql": 1}',
        '{"description": "d", "sql": "s", "spec": []}',
    ],
)
def test_parse_arguments_invalid(arguments):
    # The message is pydantic's, so only the exception is checked.
    with pytest.raises(InvalidToolCall):
        parse_arguments("query", arguments)
