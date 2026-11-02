from fakes import RESULT, FakeEngine
from glint.agent import run_tool_call
from glint.history import InvalidCall, QueryResult, ToolCall


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
