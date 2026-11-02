import json

from fakes import RESULT, FakeEndpoint, FakeEngine
from glint import agent
from glint.agent import Session, run_tool_call
from glint.history import AssistantMessage, InvalidCall, QueryResult, ToolCall, UserMessage
from glint.tool import QUERY_TOOL

CALL = ToolCall("call_1", "query", '{"description": "Films per rating", "sql": "SELECT 1"}')
ANSWER = AssistantMessage("There are 178 G-rated films.")


def test_respond_without_tool_calls():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine())
    entries = list(session.respond("How many G films?"))
    assert entries == [UserMessage("How many G films?"), ANSWER]
    assert list(session.history) == entries
    [request] = endpoint.requests
    assert request["model"] == "fake-model"
    assert request["messages"] == [{"role": "user", "content": "How many G films?"}]
    assert request["tools"] == [QUERY_TOOL]


def test_respond_with_tool_call():
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL,)), ANSWER)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine)
    entries = list(session.respond("How many G films?"))
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, AssistantMessage]
    assert entries[1] == AssistantMessage(None, (CALL,))
    assert entries[2].run.result == RESULT
    assert engine.queries == ["SELECT 1"]
    # The second request carries the call and its result, and nothing the model shouldn't see.
    tool_message = endpoint.requests[1]["messages"][2]
    assert tool_message.keys() == {"role", "tool_call_id", "content"}
    assert json.loads(tool_message["content"]) == {"columns": ["rating", "n"], "rows": [["G", 178]]}


def test_respond_keeps_earlier_turns():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine())
    list(session.respond("first"))
    list(session.respond("second"))
    assert [m["content"] for m in endpoint.requests[1]["messages"]] == ["first", ANSWER.text, "second"]


def test_respond_stops_after_max_steps(monkeypatch):
    monkeypatch.setattr(agent, "MAX_STEPS", 3)
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL,)))
    session = Session(endpoint.client(), "fake-model", FakeEngine())
    entries = list(session.respond("loop"))
    assert len(endpoint.requests) == 3
    assert entries[-1] == AssistantMessage("Stopped after 3 steps without an answer.")


def test_run_tool_call():
    entry = run_tool_call(FakeEngine(), ToolCall("call_1", "query", '{"description": "Films", "sql": "SELECT 1"}'))
    assert isinstance(entry, QueryResult)
    assert entry.tool_call_id == "call_1"
    assert (entry.run.description, entry.run.sql, entry.run.result) == ("Films", "SELECT 1", RESULT)


def test_run_tool_call_malformed():
    engine = FakeEngine()
    entry = run_tool_call(engine, ToolCall("call_1", "query", '{"description": "Films"}'))
    assert engine.queries == []
    assert isinstance(entry, InvalidCall)
    assert entry.tool_call_id == "call_1"


def test_run_tool_call_unknown_tool():
    entry = run_tool_call(FakeEngine(), ToolCall("call_1", "execute", "{}"))
    assert entry == InvalidCall("call_1", "unknown tool execute")
