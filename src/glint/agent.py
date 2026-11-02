"""The agent loop: the model calls the query tool until it answers."""

from typing import Any

from openai.types.chat import ChatCompletionMessageFunctionToolCall

from glint.engine import Engine
from glint.tool import InvalidToolCall, parse_arguments, run_query


def run_tool_call(engine: Engine, tool_call: ChatCompletionMessageFunctionToolCall) -> dict[str, Any]:
    """Run one of the model's tool calls and return the history entry answering it.

    content is what the model sees. A call that parses also carries its
    query_run, for the page; a malformed one gets only an error to fix.
    """
    message = {"role": "tool", "tool_call_id": tool_call.id}
    try:
        args = parse_arguments(tool_call.function.name, tool_call.function.arguments)
    except InvalidToolCall as e:
        return {**message, "content": f"error: {e}"}
    run = run_query(engine, args.description, args.sql, args.spec)
    return {**message, "content": run.content(), "query_run": run}
