import threading

import pytest

from fakes import RAW_RESULT, FakeEndpoint, FakeEngine
from glint.agent import Session, beliefs_message, run_tool_call, skip_tool_call
from glint.prompt import LAST_STEP_NOTE, REVISE_NOTE, system_prompt
from glint.history import (
    AssistantMessage,
    BeliefRevision,
    History,
    InvalidCall,
    QueryResult,
    ToolCall,
    Usage,
    UserMessage,
    to_api,
)
from glint.serialize import Result
from glint.tool import QUERY_TOOL, REVISE_BELIEFS_TOOL

CALL = ToolCall("call_1", "query", '{"description": "Films per rating", "sql": "SELECT 1"}')
ANSWER = AssistantMessage("There are 178 G-rated films.", model="fake-model", final=True)
CALL_REPLY = AssistantMessage(None, (CALL,), model="fake-model")


def revise(arguments: str) -> AssistantMessage:
    """A reply revising the beliefs."""
    return AssistantMessage(None, (ToolCall("call_0", "revise_beliefs", arguments),), Usage(50, 5), "fake-model")


# A revision that changes nothing.
NOTED = revise('{"drop": [], "add": []}')


def sent(request) -> list:
    """What the request sent after the system prompt."""
    assert request["messages"][0]["role"] == "system"
    return request["messages"][1:]


def context(beliefs, *entries) -> list:
    """The beliefs, then the conversation and the recent observations as they happened."""
    return [{"role": "user", "content": beliefs_message(beliefs)}, *map(to_api, entries)]


def revising_context(beliefs, *entries) -> list:
    """The context, then Glint's note asking for a revision."""
    return [*context(beliefs, *entries), {"role": "user", "content": REVISE_NOTE}]


def test_respond_without_tool_calls():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    entries = list(session.respond("How many G films?"))
    assert entries == [UserMessage("How many G films?"), ANSWER]
    assert list(session.history) == entries
    [request] = endpoint.requests
    assert request["model"] == "fake-model"
    assert request["messages"] == [
        {"role": "system", "content": system_prompt(100, 200, 10)},
        {"role": "user", "content": beliefs_message({})},
        {"role": "user", "content": "How many G films?"},
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
    answer = AssistantMessage("There are 178 G-rated films.", usage=Usage(120, 8), model="fake-model", final=True)
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
    # The call and its result are sent as they happened, and nothing the model shouldn't see.
    assert sent(endpoint.requests[1]) == context({}, *entries[0:3])
    assert sent(endpoint.requests[1])[-1].keys() == {"role", "tool_call_id", "content"}


def test_respond_revises_every_max_observations():
    belief = {1: "There are 178 G-rated films."}
    endpoint = FakeEndpoint(CALL_REPLY, revise('{"drop": [], "add": ["There are 178 G-rated films."]}'), ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), max_observations=1)
    entries = list(session.respond("How many G films?"))
    # The revising reply is recorded as its revision, with its tokens and model.
    assert [type(e) for e in entries] == [UserMessage, AssistantMessage, QueryResult, BeliefRevision, AssistantMessage]
    assert entries[3] == BeliefRevision({}, belief, Usage(50, 5), "fake-model")
    assert session.beliefs.current == belief
    act, revising, answer = endpoint.requests
    assert act["tools"] == [QUERY_TOOL]
    # After one observation, the model must revise, seeing it.
    assert revising["tools"] == [REVISE_BELIEFS_TOOL]
    assert revising["tool_choice"] == "required"
    assert sent(revising) == revising_context({}, *entries[0:3])
    # Revising doesn't clear what the model sees.
    assert sent(answer) == context(belief, *entries[0:3])


def test_respond_records_the_revision_reasoning():
    reply = AssistantMessage(
        None, NOTED.tool_calls, model="fake-model", reasoning="The result changes nothing I believe."
    )
    endpoint = FakeEndpoint(CALL_REPLY, reply, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), max_observations=1)
    entries = list(session.respond("How many G films?"))
    assert entries[3] == BeliefRevision({}, {}, None, "fake-model", "The result changes nothing I believe.")


def test_respond_forgets_the_oldest_observation():
    endpoint = FakeEndpoint(CALL_REPLY, NOTED, CALL_REPLY, NOTED, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), max_observations=1)
    entries = list(session.respond("How many G films?"))
    user, first_reply, first_result, _, second_reply, second_result, _, answer = entries
    # The first observation has left; the user's message stays.
    assert sent(endpoint.requests[-1]) == context({}, user, second_reply, second_result)


def test_respond_records_what_dropped_beliefs_said():
    history = History()
    history.extend(BeliefRevision({}, {1: "Most films are rated G.", 2: "Films have ratings."}))
    reply = revise('{"drop": [1], "add": ["Few films are rated G."]}')
    endpoint = FakeEndpoint(CALL_REPLY, reply, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), history, max_observations=1)
    entries = list(session.respond("Check the ratings."))
    assert entries[3] == BeliefRevision({1: "Most films are rated G."}, {3: "Few films are rated G."}, Usage(50, 5), "fake-model")
    assert session.beliefs.current == {2: "Films have ratings.", 3: "Few films are rated G."}


@pytest.mark.parametrize(
    "arguments",
    [
        '{"drop": [], "add": "One statement."}',  # not a list
        '{"drop": [1], "add": []}',  # not held
    ],
)
def test_respond_retries_an_invalid_revision(arguments):
    invalid = revise(arguments)
    endpoint = FakeEndpoint(CALL_REPLY, invalid, NOTED, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), max_observations=1)
    entries = list(session.respond("How many G films?"))
    user, call_reply, result, reply, error, revision, answer = entries
    assert reply == invalid
    assert error.tool_call_id == "call_0"
    assert error.error.startswith("Not applied: ")
    assert revision == BeliefRevision({}, {}, Usage(50, 5), "fake-model")
    # The retry sees the failed call and its error, and must revise again.
    retry = endpoint.requests[2]
    assert sent(retry) == revising_context({}, user, call_reply, result, reply, error)
    assert retry["tools"] == [REVISE_BELIEFS_TOOL]


def test_respond_retries_without_a_revision():
    # A model that answers when it must revise, though the request requires a call.
    endpoint = FakeEndpoint(CALL_REPLY, ANSWER, NOTED, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History(), max_observations=1)
    entries = list(session.respond("How many G films?"))
    assert [type(e) for e in entries] == [
        UserMessage, AssistantMessage, QueryResult, AssistantMessage, BeliefRevision, AssistantMessage
    ]
    # The failed revision isn't an answer: the turn goes on.
    assert not entries[3].final
    assert endpoint.requests[2]["tools"] == [REVISE_BELIEFS_TOOL]


def test_respond_continues_saved_history(tmp_path):
    path = tmp_path / "history.jsonl"
    first_endpoint = FakeEndpoint(CALL_REPLY, ANSWER)
    first = Session(first_endpoint.client(), "fake-model", FakeEngine(), History(path), max_observations=2)
    earlier = list(first.respond("How many G films?"))
    endpoint = FakeEndpoint(NOTED, ANSWER)
    second = Session(endpoint.client(), "fake-model", FakeEngine(), History(path), max_observations=1)
    list(second.respond("And PG films?"))
    # The conversation, the recent observations and the count since the last revision come back from the saved
    # history. The earlier observation is sent between the question and the answer it led to.
    assert endpoint.requests[0]["tools"] == [REVISE_BELIEFS_TOOL]
    assert sent(endpoint.requests[0]) == revising_context({}, *earlier, UserMessage("And PG films?"))


def test_stopping_early_leaves_valid_history():
    # As when the browser disconnects: the caller stops right after the tool call.
    endpoint = FakeEndpoint(CALL_REPLY, ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    turn = session.respond("How many G films?")
    assert next(turn) == UserMessage("How many G films?")
    assert next(turn) == CALL_REPLY
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


def test_respond_stops_after_max_steps():
    # The fake calls the tool on the last step too, though none is offered.
    endpoint = FakeEndpoint(CALL_REPLY)
    engine = FakeEngine()
    session = Session(endpoint.client(), "fake-model", engine, History(), max_steps=3)
    entries = list(session.respond("loop"))
    assert ["tools" in r for r in endpoint.requests] == [True, True, False]
    note = {"role": "user", "content": LAST_STEP_NOTE}
    assert [r["messages"][-1] == note for r in endpoint.requests] == [False, False, True]
    assert UserMessage(LAST_STEP_NOTE) not in session.history
    assert len(engine.queries) == 2  # the last step's call is skipped
    assert entries[-2].run.error == "Canceled."
    assert entries[-1] == AssistantMessage("Stopped after 3 steps without an answer.", final=True)


def test_interrupt_before_the_next_request():
    endpoint = FakeEndpoint(ANSWER)
    session = Session(endpoint.client(), "fake-model", FakeEngine(), History())
    turn = session.respond("How many G films?")
    next(turn)
    session.interrupt()
    assert list(turn) == [AssistantMessage("Interrupted.", final=True)]
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
    assert entries[4] == AssistantMessage("Interrupted.", final=True)


def test_interrupt_between_turns_is_ignored():
    session = Session(FakeEndpoint(ANSWER).client(), "fake-model", FakeEngine(), History())
    session.interrupt()
    assert list(session.respond("How many G films?"))[-1] == ANSWER


def test_beliefs_message():
    assert beliefs_message({1: "The user likes films.", 3: "Films have ratings."}) == """\
Glint: Here is what you believe about the world:
1. The user likes films.
3. Films have ratings."""


def test_beliefs_message_without_beliefs():
    assert beliefs_message({}) == """\
Glint: Here is what you believe about the world:
Nothing yet."""


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
