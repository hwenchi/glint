import pytest

from fakes import RAW_RESULT, FakeEngine
from glint.engine import QueryError
from glint.serialize import Result
from glint.tool import (
    QUERY_TOOL,
    REVISE_BELIEFS_TOOL,
    InvalidToolCall,
    QueryArgs,
    ReviseBeliefsArgs,
    parse_arguments,
    parse_revise_beliefs_arguments,
    run_query,
)


def test_run_query():
    engine = FakeEngine()
    run = run_query(engine, "Films per rating", "SELECT rating, count(*) AS n FROM film GROUP BY rating")
    assert engine.queries == ["SELECT rating, count(*) AS n FROM film GROUP BY rating"]
    assert (run.result, run.error, run.spec) == (Result.from_raw(RAW_RESULT), None, None)


def test_run_query_with_spec_gets_description():
    spec = {"mark": "bar"}
    run = run_query(FakeEngine(), "Films per rating", "SELECT 1", spec)
    assert run.spec == {"description": "Films per rating", "mark": "bar"}
    assert spec == {"mark": "bar"}


def test_run_query_keeps_spec_description():
    run = run_query(FakeEngine(), "Films per rating", "SELECT 1", {"description": "Own", "mark": "bar"})
    assert run.spec["description"] == "Own"


def test_url_fails_the_run_without_querying():
    engine = FakeEngine()
    run = run_query(engine, "Films", "SELECT 1", {"mark": "bar", "encoding": {"href": {"field": "x"}}})
    assert engine.queries == []
    assert run.result is None
    assert run.error.startswith("$.encoding.href:")


def test_query_error():
    run = run_query(FakeEngine(error=QueryError('column "nope" does not exist')), "Films", "SELECT nope")
    assert run.result is None
    assert run.error == 'column "nope" does not exist'


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
    assert str(e.value) == "Unknown tool: execute."


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


def test_revise_beliefs_tool_matches_args():
    # REVISE_BELIEFS_TOOL is written for the model and ReviseBeliefsArgs parses its calls.
    parameters = REVISE_BELIEFS_TOOL["function"]["parameters"]
    assert list(parameters["properties"]) == list(ReviseBeliefsArgs.model_fields)
    assert parameters["required"] == [n for n, f in ReviseBeliefsArgs.model_fields.items() if f.is_required()]


def test_parse_revise_beliefs_arguments():
    arguments = '{"drop": [3], "add": ["101 recipes are tagged low-sodium."]}'
    assert parse_revise_beliefs_arguments("revise_beliefs", arguments) == ReviseBeliefsArgs(
        drop=[3], add=["101 recipes are tagged low-sodium."]
    )


def test_parse_revise_beliefs_arguments_unknown_tool():
    with pytest.raises(InvalidToolCall) as e:
        parse_revise_beliefs_arguments("query", '{"drop": [], "add": []}')
    assert str(e.value) == "Unknown tool: query."


@pytest.mark.parametrize(
    "arguments",
    [
        '{"drop": []}',
        '{"drop": [], "add": "One statement."}',  # not a list
        '{"drop": ["1"], "add": []}',  # not a number
        '{"drop": [], "add": [], "keep": []}',  # not in the schema
    ],
)
def test_parse_revise_beliefs_arguments_invalid(arguments):
    with pytest.raises(InvalidToolCall):
        parse_revise_beliefs_arguments("revise_beliefs", arguments)
