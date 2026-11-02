"""The agent loop: the model calls the query tool until it answers."""

from glint.engine import Engine
from glint.history import InvalidCall, QueryResult, ToolCall
from glint.tool import InvalidToolCall, parse_arguments, run_query


def run_tool_call(engine: Engine, call: ToolCall) -> QueryResult | InvalidCall:
    """Run one of the model's tool calls and return the history entry answering it."""
    try:
        args = parse_arguments(call.name, call.arguments)
    except InvalidToolCall as e:
        return InvalidCall(call.id, str(e))
    run = run_query(engine, args.description, args.sql, args.spec)
    return QueryResult(call.id, run)
