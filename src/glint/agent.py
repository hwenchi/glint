"""The agent loop: the model calls the query tool until it answers."""

from collections.abc import Iterator, Sequence

from openai import OpenAI

from glint.engine import Engine
from glint.history import AssistantMessage, Entry, InvalidCall, QueryResult, ToolCall, UserMessage, from_api, to_api
from glint.prompt import SYSTEM_PROMPT
from glint.tool import QUERY_TOOL, InvalidToolCall, parse_arguments, run_query

# Model requests per user message, so a model that keeps calling the tool
# can't run forever.
MAX_STEPS = 20

SYSTEM_MESSAGE = {"role": "system", "content": SYSTEM_PROMPT}


class Session:
    """The one conversation of this Glint process. Only respond adds to its history."""

    def __init__(self, client: OpenAI, model: str, engine: Engine):
        self.client = client
        self.model = model
        self.engine = engine
        self._history: list[Entry] = []

    @property
    def history(self) -> Sequence[Entry]:
        """Everything so far, for showing the page. Read-only."""
        return self._history

    def respond(self, text: str) -> Iterator[Entry]:
        """Answer the user's message: ask the model and run its tool calls until it replies without any.

        Each new entry is added to the history and yielded, so it can be shown as it arrives.
        """
        yield self._add(UserMessage(text))
        for _ in range(MAX_STEPS):
            messages = [SYSTEM_MESSAGE] + [to_api(entry) for entry in self._history]
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=[QUERY_TOOL])
            reply = self._add(from_api(response.choices[0].message))
            yield reply
            if not reply.tool_calls:
                return
            for call in reply.tool_calls:
                yield self._add(run_tool_call(self.engine, call))
        yield self._add(AssistantMessage(f"Stopped after {MAX_STEPS} steps without an answer."))

    def _add[E: Entry](self, entry: E) -> E:
        self._history.append(entry)
        return entry


def run_tool_call(engine: Engine, call: ToolCall) -> QueryResult | InvalidCall:
    """Run one of the model's tool calls and return the history entry answering it."""
    try:
        args = parse_arguments(call.name, call.arguments)
    except InvalidToolCall as e:
        return InvalidCall(call.id, str(e))
    run = run_query(engine, args.description, args.sql, args.spec)
    return QueryResult(call.id, run)
