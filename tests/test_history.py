import json
from datetime import UTC, datetime

import pytest
from openai.types.chat import ChatCompletionMessage
from pydantic import TypeAdapter

from fakes import RAW_RESULT
from glint.history import (
    AssistantMessage,
    BeliefRevision,
    Entry,
    History,
    InvalidCall,
    QueryResult,
    ToolCall,
    UserMessage,
    from_api,
    to_api,
)
from glint.serialize import Result
from glint.tool import QueryRun

AT = datetime(2026, 11, 1, tzinfo=UTC)
CALL = ToolCall("call_1", "query", '{"description": "d", "sql": "SELECT 1"}')


def test_user_message():
    assert to_api(UserMessage("hi")) == {"role": "user", "content": "hi"}


def test_assistant_message():
    # The reasoning is for the page only.
    assert to_api(AssistantMessage("hello", reasoning="Greet back.")) == {"role": "assistant", "content": "hello"}


def test_assistant_message_with_tool_calls():
    assert to_api(AssistantMessage(None, (CALL,))) == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "query", "arguments": CALL.arguments}}],
    }


def test_query_result():
    run = QueryRun(description="d", sql="SELECT 1", spec=None, at=AT, result=Result.from_raw(RAW_RESULT), error=None)
    message = to_api(QueryResult("call_1", run))
    assert (message["role"], message["tool_call_id"]) == ("tool", "call_1")
    assert json.loads(message["content"]) == {"columns": ["rating", "n"], "rows": [["G", 178]]}


def test_query_result_error():
    run = QueryRun(description="d", sql="SELECT nope", spec=None, at=AT, result=None, error='column "nope" does not exist')
    assert to_api(QueryResult("call_1", run)) == {
        "role": "tool", "tool_call_id": "call_1", "content": 'Error: column "nope" does not exist',
    }


def test_invalid_call():
    assert to_api(InvalidCall("call_1", "Unknown tool: execute.")) == {
        "role": "tool", "tool_call_id": "call_1", "content": "Error: Unknown tool: execute.",
    }


def test_history_json():
    # What the page receives: each entry tagged with its kind, and back again.
    run = QueryRun(description="d", sql="SELECT 1", spec=None, at=AT, result=Result.from_raw(RAW_RESULT), error=None)
    history = [
        UserMessage("hi"),
        AssistantMessage(None, (CALL,)),
        QueryResult("call_1", run),
        InvalidCall("call_2", "e"),
        BeliefRevision({1: "The user is here."}, {2: "The user greeted me."}),
    ]
    adapter = TypeAdapter(list[Entry])
    data = json.loads(adapter.dump_json(history))
    assert [e["kind"] for e in data] == ["user", "assistant", "query_result", "invalid_call", "belief_revision"]
    assert adapter.validate_python(data) == history


def test_history_in_memory():
    history = History()
    history.extend(UserMessage("hi"))
    assert history.entries == [UserMessage("hi")]


def test_history_saved_and_reloaded(tmp_path):
    path = tmp_path / "history.jsonl"
    run = QueryRun(description="d", sql="SELECT 1", spec=None, at=AT, result=Result.from_raw(RAW_RESULT), error=None)
    entries = [UserMessage("hi\nthere"), AssistantMessage(None, (CALL,)), QueryResult("call_1", run)]
    History(path).extend(*entries)
    assert len(path.read_text().splitlines()) == len(entries)  # one per line, newlines in text escaped
    assert History(path).entries == entries
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]  # no temp file left behind


def test_history_starts_empty_without_a_file(tmp_path):
    assert History(tmp_path / "history.jsonl").entries == []


def message(**fields):
    return ChatCompletionMessage.model_validate({"role": "assistant", **fields})


def test_from_api_text():
    assert from_api(message(content="hello"), "m") == AssistantMessage("hello", model="m")


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_from_api_reasoning(field):
    reply = message(content="hello", **{field: "Greet back."})
    assert from_api(reply, "m") == AssistantMessage("hello", model="m", reasoning="Greet back.")


def test_from_api_function_call():
    reply = message(content=None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "query", "arguments": CALL.arguments}},
    ])
    assert from_api(reply, "m") == AssistantMessage(None, (CALL,), model="m")


def test_from_api_custom_call():
    reply = message(content=None, tool_calls=[
        {"id": "call_2", "type": "custom", "custom": {"name": "shell", "input": "ls"}},
    ])
    assert from_api(reply, "m") == AssistantMessage(None, (ToolCall("call_2", "shell", "ls"),), model="m")
