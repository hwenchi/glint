"""The agent loop: the model calls the query tool until it answers."""

import threading
from collections.abc import Iterator, Sequence

from openai import OpenAI

from glint.engine import Engine
from glint.history import (
    AssistantMessage,
    Entry,
    History,
    InvalidCall,
    QueryResult,
    ToolCall,
    UserMessage,
    from_api,
    to_api,
)
from glint.prompt import SYSTEM_PROMPT
from glint.tool import QUERY_TOOL, InvalidToolCall, parse_arguments, run_query

# Model requests per user message, so a model that keeps calling the tool
# can't run forever.
MAX_STEPS = 20

SYSTEM_MESSAGE = {"role": "system", "content": SYSTEM_PROMPT}


class Session:
    """The one conversation of this Glint process. Only respond adds to its history."""

    def __init__(self, client: OpenAI, model: str, engine: Engine, history: History):
        self.client = client
        self.model = model
        self.engine = engine
        self._history = history
        # A plain Lock, not an RLock: a turn's steps may run on different threads,
        # so it can be released by a thread other than the one that acquired it.
        self._turn = threading.Lock()

    @property
    def history(self) -> Sequence[Entry]:
        """Everything so far, for showing the page. Read-only."""
        return self._history.entries

    def respond(self, text: str) -> Iterator[Entry]:
        """Answer the user's message: ask the model and run its tool calls until it replies without any.

        Each new entry is added to the history and yielded, so it can be shown as it arrives.
        The history is valid for the API at every yield, so stopping early is safe.
        Turns don't overlap: a second one waits until the first has ended.
        """
        with self._turn:
            user_message = UserMessage(text)
            self._history.extend(user_message)
            yield user_message
            for _ in range(MAX_STEPS):
                messages = [SYSTEM_MESSAGE, *(to_api(entry) for entry in self._history.entries)]
                response = self.client.chat.completions.create(model=self.model, messages=messages, tools=[QUERY_TOOL])
                reply = from_api(response.choices[0].message)
                results = [run_tool_call(self.engine, call) for call in reply.tool_calls]
                # Added together: the API rejects a tool call that has no result after it.
                self._history.extend(reply, *results)
                yield reply
                yield from results
                if not reply.tool_calls:
                    return
            stop_message = AssistantMessage(f"Stopped after {MAX_STEPS} steps without an answer.")
            self._history.extend(stop_message)
            yield stop_message


def run_tool_call(engine: Engine, call: ToolCall) -> QueryResult | InvalidCall:
    """Run one of the model's tool calls and return the history entry answering it."""
    try:
        args = parse_arguments(call.name, call.arguments)
    except InvalidToolCall as e:
        return InvalidCall(call.id, str(e))
    run = run_query(engine, args.description, args.sql, args.spec)
    return QueryResult(call.id, run)
