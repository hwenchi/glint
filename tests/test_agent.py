import threading
from datetime import UTC, datetime

import pytest

from fakes import RAW_RESULT, FakeEndpoint, FakeEngine
from glint.agent import Session, context_message, run_tool_call, skip_tool_call
from glint.prompt import LAST_STEP_NOTE, system_prompt
from glint.history import (
    AssistantMessage,
    BeliefRevision,
    History,
    InvalidCall,
    QueryResult,
    ToolCall,
    Usage,
    UserMessage,
)
from glint.serialize import Result
from glint.tool import QUERY_TOOL, REVISE_BELIEFS_TOOL, QueryRun

AT = datetime(2026, 11, 1, tzinfo=UTC)
CALL = ToolCall("call_1", "query", '{"description": "Films per rating", "sql": "SELECT 1"}')
ANSWER = AssistantMessage("There are 178 G-rated films.", model="fake-model")
CALL_REPLY = AssistantMessage(None, (CALL,), model="fake-model")


def revise(arguments: str) -> AssistantMessage:
    """A reply revising the beliefs."""
    return AssistantMessage(None, (ToolCall("call_0", "revise_beliefs", arguments),), Usage(50, 5), "fake-model")


# A revision that changes nothing.
NOTED = revise('{"drop": [], "add": []}')


def context(request) -> str:
    """The request's message to the model: its beliefs and its last few steps."""
    [system, user] = request["messages"]
    assert system["role"] == "system"
    return user["content"]


def test_respond_without_tool_calls():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    entries = list(session.respond("How many G films?"))
    assert entries == [UserMessage("How many G films?"), ANSWER]
    assert list(session.history) == entries
    [request] = endpoint.requests
    assert request["model"] == "fake-model"
    assert request["messages"] == [
        {"role": "system", "content": system_prompt(100, 50, 10)},
        {"role": "user", "content": context_message({}, [UserMessage("How many G films?")])},
    ]
    assert request["tools"] == [QUERY_TOOL]
    assert "tool_choice" not in request
    assert "reasoning_effort" not in request


def test_respond_sends_reasoning_effort():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), reasoning_effort="medium")
    list(session.respond("How many G films?"))
    [request] = endpoint.requests
    assert request["reasoning_effort"] == "medium"


def test_respond_records_usage():
    answer = AssistantMessage("There are 178 G-rated films.", usage=Usage(120, 8), model="fake-model")
    session = Session(FakeEndpoint(answer).client(), "fake-model", FakeEngine(), History())
    assert list(session.respond("How many G films?"))[-1] == answer


def test_respond_with_tool_call():
    endpoint = FakeEndpoint(CALL_REPLY, ANSWER)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine, History())
    entries = list(session.respond("How many G films?"))
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, AssistantMessage]
    assert entries[2].run.result == Result.from_raw(RAW_RESULT)
    assert engine.queries == ["SELECT 1"]
    assert context(endpoint.requests[1]) == context_message({}, entries[:3])


def test_respond_revises_every_recent_steps():
    belief = {1: "The user wants G films counted."}
    endpoint = FakeEndpoint(CALL_REPLY, revise('{"drop": [], "add": ["The user wants G films counted."]}'), ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), recent_steps=2)
    entries = list(session.respond("How many G films?"))
    # The revising reply is recorded as its revision, with its tokens and model.
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, BeliefRevision, AssistantMessage]
    assert entries[3] == BeliefRevision({}, belief, Usage(50, 5), "fake-model")
    assert session.beliefs.current == belief
    act, revising, answer = endpoint.requests
    assert act["tools"] == [QUERY_TOOL]
    # After two steps, the model must revise, seeing both.
    assert revising["tools"] == [REVISE_BELIEFS_TOOL]
    assert revising["tool_choice"] == "required"
    assert context(revising) == context_message({}, entries[:3])
    # Revising doesn't clear what the model sees.
    assert context(answer) == context_message(belief, entries[:3])


def test_respond_forgets_the_oldest_step():
    endpoint = FakeEndpoint(CALL_REPLY, NOTED, CALL_REPLY, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), recent_steps=2)
    entries = list(session.respond("How many G films?"))
    user, first_reply, first_result, revision, second_reply, second_result, answer = entries
    # Two steps in view: the user's message has left.
    assert context(endpoint.requests[-1]) == context_message({}, [first_reply, first_result, second_reply, second_result])


def test_respond_records_what_dropped_beliefs_said():
    history = History()
    history.extend(BeliefRevision({}, {1: "Most films are rated G.", 2: "The user likes films."}))
    reply = revise('{"drop": [1], "add": ["Few films are rated G."]}')
    session = Session(FakeEndpoint(reply, ANSWER).client(), "fake-model", FakeEngine(), history, recent_steps=1)
    entries = list(session.respond("Check the ratings."))
    assert entries[1] == BeliefRevision({1: "Most films are rated G."}, {3: "Few films are rated G."}, Usage(50, 5), "fake-model")
    assert session.beliefs.current == {2: "The user likes films.", 3: "Few films are rated G."}


@pytest.mark.parametrize(
    "arguments",
    [
        '{"drop": [], "add": "One statement."}',  # not a list
        '{"drop": [1], "add": []}',  # not held
    ],
)
def test_respond_stops_on_an_invalid_revision(arguments):
    session = Session(FakeEndpoint(revise(arguments)).client(), "fake-model", FakeEngine(), History(), recent_steps=1)
    entries = list(session.respond("How many G films?"))
    assert len(entries) == 2
    assert entries[1].text.startswith("Stopped: the model's revision of its beliefs was invalid.")
    assert session.beliefs.current == {}


def test_respond_stops_without_a_revision():
    # A model that answers when it must revise, though the request requires a call.
    session = Session(FakeEndpoint(ANSWER).client(), "fake-model", FakeEngine(), History(), recent_steps=1)
    entries = list(session.respond("How many G films?"))
    assert entries == [UserMessage("How many G films?"), AssistantMessage("Stopped: the model didn't revise its beliefs.")]


def test_respond_continues_saved_history(tmp_path):
    path = tmp_path / "history.jsonl"
    first_endpoint = FakeEndpoint(revise('{"drop": [], "add": ["The user likes films."]}'), ANSWER)
    first = Session(first_endpoint.client(), "fake-model", FakeEngine(), History(path), recent_steps=1)
    list(first.respond("I like films."))
    endpoint = FakeEndpoint(NOTED, ANSWER)
    second = Session(endpoint.client(), "fake-model", FakeEngine(), History(path), recent_steps=2)
    list(second.respond("How many G films?"))
    # The beliefs, the recent steps and the count since the last revision come back from the saved history.
    assert endpoint.requests[0]["tools"] == [REVISE_BELIEFS_TOOL]
    assert context(endpoint.requests[0]) == context_message({1: "The user likes films."}, [ANSWER, UserMessage("How many G films?")])


def test_stopping_early_keeps_what_was_recorded():
    # As when the browser disconnects: the caller stops right after the reply.
    endpoint = FakeEndpoint(CALL_REPLY, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    turn = session.respond("How many G films?")
    assert next(turn) == UserMessage("How many G films?")
    assert next(turn) == CALL_REPLY
    turn.close()
    assert list(session.history) == [UserMessage("How many G films?"), CALL_REPLY]


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


def test_respond_stops_after_max_steps():
    # The fake calls the tool on the last step too, though none is offered.
    endpoint = FakeEndpoint(CALL_REPLY)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine, History(), max_steps=3)
    entries = list(session.respond("loop"))
    assert ["tools" in r for r in endpoint.requests] == [True, True, False]
    assert [context(r).endswith(LAST_STEP_NOTE) for r in endpoint.requests] == [False, False, True]
    assert len(engine.queries) == 2  # the last step's call is skipped
    assert entries[-2].run.error == "Canceled."
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


def test_context_message():
    result = Result.from_raw(RAW_RESULT)
    recent = [
        AssistantMessage("Let me count them.", (CALL, CALL)),
        QueryResult("call_1", QueryRun(description="Films by rating", sql="SELECT 1", spec=None, at=AT, result=result, error=None)),
        QueryResult("call_2", QueryRun(description="Nope", sql="SELECT nope", spec=None, at=AT, result=None, error="no column")),
        InvalidCall("call_3", "Unknown tool: execute."),
    ]
    assert context_message({1: "The user likes films.", 3: "Films have ratings."}, recent) == """\
Here is what you believe about the world:
1. The user likes films.
3. Films have ratings.

And what happened recently:

You replied:
Let me count them.

You ran a query: Films by rating
SELECT 1
Result: {"columns":["rating","n"],"rows":[["G",178]]}

You ran a query: Nope
SELECT nope
Error: no column

Your query couldn't be run: Unknown tool: execute."""


def test_context_message_without_beliefs():
    assert context_message({}, [UserMessage("hi")]) == """\
Here is what you believe about the world:
Nothing yet.

And what happened recently:

The user wrote:
hi"""


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
