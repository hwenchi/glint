import json

from openai.types.chat import ChatCompletionMessageFunctionToolCall

from fakes import RESULT, FakeEngine
from glint.agent import run_tool_call


def tool_call(arguments, name="query"):
    return ChatCompletionMessageFunctionToolCall.model_validate(
        {"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}
    )


def test_run_tool_call():
    message = run_tool_call(FakeEngine(), tool_call('{"description": "Films", "sql": "SELECT 1"}'))
    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_1"
    assert json.loads(message["content"]) == {"columns": ["rating", "n"], "rows": [["G", 178]]}
    assert (message["query_run"].sql, message["query_run"].result) == ("SELECT 1", RESULT)


def test_run_tool_call_malformed():
    engine = FakeEngine()
    message = run_tool_call(engine, tool_call('{"description": "Films"}'))
    assert engine.queries == []
    assert message["content"].startswith("error: ")
    assert "query_run" not in message


def test_run_tool_call_unknown_tool():
    message = run_tool_call(FakeEngine(), tool_call("{}", name="execute"))
    assert message["content"] == "error: unknown tool execute"
