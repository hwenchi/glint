import json
from datetime import UTC, datetime

from openai.types.chat import ChatCompletionMessage

from fakes import RESULT
from glint.history import (
    AssistantMessage,
    InvalidCall,
    QueryResult,
    ToolCall,
    UserMessage,
    from_api,
    to_api,
)
from glint.serialize import result_data
from glint.tool import QueryRun

AT = datetime(2026, 11, 1, tzinfo=UTC)
CALL = ToolCall("call_1", "query", '{"description": "d", "sql": "SELECT 1"}')


def test_user_message():
    assert to_api(UserMessage("hi")) == {"role": "user", "content": "hi"}


def test_assistant_message():
    assert to_api(AssistantMessage("hello")) == {"role": "assistant", "content": "hello"}


def test_assistant_message_with_tool_calls():
    assert to_api(AssistantMessage(None, (CALL,))) == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "query", "arguments": CALL.arguments}}],
    }


def test_query_result():
    run = QueryRun(description="d", sql="SELECT 1", spec=None, at=AT, result=result_data(RESULT), error=None)
    message = to_api(QueryResult("call_1", run))
    assert (message["role"], message["tool_call_id"]) == ("tool", "call_1")
    assert json.loads(message["content"]) == {"columns": ["rating", "n"], "rows": [["G", 178]]}


def test_query_result_error():
    run = QueryRun(description="d", sql="SELECT nope", spec=None, at=AT, result=None, error='column "nope" does not exist')
    assert to_api(QueryResult("call_1", run)) == {
        "role": "tool", "tool_call_id": "call_1", "content": 'error: column "nope" does not exist',
    }


def test_invalid_call():
    assert to_api(InvalidCall("call_1", "unknown tool execute")) == {
        "role": "tool", "tool_call_id": "call_1", "content": "error: unknown tool execute",
    }


def message(**fields):
    return ChatCompletionMessage.model_validate({"role": "assistant", **fields})


def test_from_api_text():
    assert from_api(message(content="hello")) == AssistantMessage("hello")


def test_from_api_function_call():
    reply = message(content=None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "query", "arguments": CALL.arguments}},
    ])
    assert from_api(reply) == AssistantMessage(None, (CALL,))


def test_from_api_custom_call():
    reply = message(content=None, tool_calls=[
        {"id": "call_2", "type": "custom", "custom": {"name": "shell", "input": "ls"}},
    ])
    assert from_api(reply) == AssistantMessage(None, (ToolCall("call_2", "shell", "ls"),))
