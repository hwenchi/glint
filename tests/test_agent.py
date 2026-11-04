import json
import threading

from fakes import RAW_RESULT, FakeEndpoint, FakeEngine
from glint import agent
from glint.agent import SYSTEM_MESSAGE, Session, run_tool_call, skip_tool_call
from glint.history import AssistantMessage, History, InvalidCall, QueryResult, ToolCall, UserMessage
from glint.serialize import Result
from glint.tool import QUERY_TOOL

CALL = ToolCall("call_1", "query", '{"description": "Films per rating", "sql": "SELECT 1"}')
ANSWER = AssistantMessage("There are 178 G-rated films.")


def test_respond_without_tool_calls():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    entries = list(session.respond("How many G films?"))
    assert entries == [UserMessage("How many G films?"), ANSWER]
    assert list(session.history) == entries
    [request] = endpoint.requests
    assert request["model"] == "fake-model"
    assert request["messages"] == [SYSTEM_MESSAGE, {"role": "user", "content": "How many G films?"}]
    assert request["tools"] == [QUERY_TOOL]


def test_respond_with_tool_call():
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL,)), ANSWER)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine, History())
    entries = list(session.respond("How many G films?"))
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, AssistantMessage]
    assert entries[1] == AssistantMessage(None, (CALL,))
    assert entries[2].run.result == Result.from_raw(RAW_RESULT)
    assert engine.queries == ["SELECT 1"]
    # The second request carries the call and its result, and nothing the model shouldn't see.
    tool_message = endpoint.requests[1]["messages"][3]
    assert tool_message.keys() == {"role", "tool_call_id", "content"}
    assert json.loads(tool_message["content"]) == {"columns": ["rating", "n"], "rows": [["G", 178]]}


def test_respond_continues_saved_history(tmp_path):
    path = tmp_path / "history.jsonl"
    first = Session(FakeEndpoint(ANSWER).client(), "fake-model", FakeEngine(), History(path))
    list(first.respond("How many G films?"))
    endpoint = FakeEndpoint(ANSWER)
    second = Session(endpoint.client(), "fake-model", FakeEngine(), History(path))
    list(second.respond("And PG?"))
    assert endpoint.requests[0]["messages"][1:] == [
        {"role": "user", "content": "How many G films?"},
        {"role": "assistant", "content": ANSWER.text},
        {"role": "user", "content": "And PG?"},
    ]


def test_stopping_early_leaves_valid_history():
    # As when the browser disconnects: the caller stops right after the tool call.
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL,)), ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    turn = session.respond("How many G films?")
    assert next(turn) == UserMessage("How many G films?")
    assert next(turn) == AssistantMessage(None, (CALL,))
    turn.close()
    assert [type(e) for e in session.history] == [UserMessage, AssistantMessage, QueryResult]


def test_turns_wait_for_each_other():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    first = session.respond("first")
    next(first)  # the first turn has started
    second = threading.Thread(target=lambda: list(session.respond("second")))
    second.start()
    second.join(timeout=0.2)
    assert second.is_alive()  # waiting for the first turn
    assert list(session.history) == [UserMessage("first")]
    list(first)
    second.join(timeout=5)
    assert [e.text for e in session.history] == ["first", ANSWER.text, "second", ANSWER.text]


def test_closing_a_turn_lets_the_next_run():
    session = Session(FakeEndpoint(ANSWER).client(), "fake-model", FakeEngine(), History())
    first = session.respond("first")
    next(first)
    first.close()
    assert list(session.respond("second"))[0] == UserMessage("second")


def test_respond_keeps_earlier_turns():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    list(session.respond("first"))
    list(session.respond("second"))
    assert endpoint.requests[1]["messages"][0] == SYSTEM_MESSAGE
    assert [m["content"] for m in endpoint.requests[1]["messages"][1:]] == ["first", ANSWER.text, "second"]


def test_respond_stops_after_max_steps(monkeypatch):
    monkeypatch.setattr(agent, "MAX_STEPS", 3)
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL,)))
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    entries = list(session.respond("loop"))
    assert len(endpoint.requests) == 3
    assert entries[-1] == AssistantMessage("Stopped after 3 steps without an answer.")


def test_interrupt_before_the_next_request():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    turn = session.respond("How many G films?")
    next(turn)
    session.interrupt()
    assert list(turn) == [AssistantMessage("Interrupted.")]
    assert endpoint.requests == []


def test_interrupt_cancels_the_remaining_tool_calls():
    second = ToolCall("call_2", "query", '{"description": "Films per year", "sql": "SELECT 2"}')
    endpoint = FakeEndpoint(AssistantMessage(None, (CALL, second)), ANSWER)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine, History())
    # The stop arrives while the first query runs.
    run_first_query = engine.query

    def query(sql):
        session.interrupt()
        return run_first_query(sql)

    engine.query = query
    entries = list(session.respond("How many G films?"))
    assert engine.queries == ["SELECT 1"]
    assert len(endpoint.requests) == 1
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, QueryResult, AssistantMessage]
    assert entries[3].run.error == "Canceled."
    assert entries[4] == AssistantMessage("Interrupted.")


def test_interrupt_between_turns_is_ignored():
    session = Session(FakeEndpoint(ANSWER).client(), "fake-model", FakeEngine(), History())
    session.interrupt()
    assert list(session.respond("How many G films?"))[-1] == ANSWER


def test_skip_tool_call_malformed():
    entry = skip_tool_call(ToolCall("call_1", "query", '{"description": "Films"}'))
    assert isinstance(entry, InvalidCall)


def test_run_tool_call():
    entry = run_tool_call(FakeEngine(), ToolCall("call_1", "query", '{"description": "Films", "sql": "SELECT 1"}'))
    assert isinstance(entry, QueryResult)
    assert entry.tool_call_id == "call_1"
    assert (entry.run.description, entry.run.sql, entry.run.result) == ("Films", "SELECT 1", Result.from_raw(RAW_RESULT))


def test_run_tool_call_malformed():
    engine = FakeEngine()
    entry = run_tool_call(engine, ToolCall("call_1", "query", '{"description": "Films"}'))
    assert engine.queries == []
    assert isinstance(entry, InvalidCall)
    assert entry.tool_call_id == "call_1"


def test_run_tool_call_unknown_tool():
    entry = run_tool_call(FakeEngine(), ToolCall("call_1", "execute", "{}"))
    assert entry == InvalidCall("call_1", "Unknown tool: execute.")
