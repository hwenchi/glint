"""The agent loop: the model calls the query tool until it answers."""

import threading
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

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
    to_api_messages,
)
from glint.prompt import system_prompt
from glint.tool import QUERY_TOOL, InvalidToolCall, QueryRun, parse_arguments, run_query


class Session:
    """The one conversation of this Glint process. Only respond adds to its history."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        engine: Engine,
        history: History,
        recent_results: int = 20,
        max_steps: int = 100,
    ):
        self.client = client
        self.model = model
        self.engine = engine
        self._history = history
        self.recent_results = recent_results  # results the model sees in full; older ones are omitted
        self.max_steps = max_steps  # model requests per user message
        self.system_message = {"role": "system", "content": system_prompt(max_steps)}
        # A plain Lock, not an RLock: a turn's steps may run on different threads,
        # so it can be released by a thread other than the one that acquired it.
        self._turn = threading.Lock()
        # Set by a stop request, which runs on another thread than the turn's steps.
        self._interrupted = threading.Event()

    @property
    def history(self) -> Sequence[Entry]:
        """Everything so far, for showing the page. Read-only."""
        return self._history.entries

    def interrupt(self) -> None:
        """End the running turn before its next model request or tool call.

        A request or query already under way finishes first.
        """
        self._interrupted.set()

    def respond(self, text: str) -> Iterator[Entry]:
        """Answer the user's message: ask the model and run its tool calls until it replies without any.

        Each new entry is added to the history and yielded, so it can be shown as it arrives.
        The history is valid for the API at every yield, so stopping early is safe.
        Turns don't overlap: a second one waits until the first has ended.
        """
        with self._turn:
            self._interrupted.clear()  # a stop sent between turns isn't for this one
            user_message = UserMessage(text)
            self._history.extend(user_message)
            yield user_message
            for step in range(self.max_steps):
                if self._interrupted.is_set():
                    interrupted = AssistantMessage("Interrupted.")
                    self._history.extend(interrupted)
                    yield interrupted
                    return
                # The last step must answer. The tool stays listed: some servers reject
                # tool messages in a request without tools.
                last = step == self.max_steps - 1
                messages = [self.system_message, *to_api_messages(self._history.entries, self.recent_results)]
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=[QUERY_TOOL], tool_choice="none" if last else "auto"
                )
                reply = from_api(response.choices[0].message)
                results = []
                for call in reply.tool_calls:
                    # Some servers ignore tool_choice, so calls on the last step are skipped.
                    if self._interrupted.is_set() or last:
                        results.append(skip_tool_call(call))
                    else:
                        results.append(run_tool_call(self.engine, call))
                # Added together: the API rejects a tool call that has no result after it.
                self._history.extend(reply, *results)
                yield reply
                yield from results
                if not reply.tool_calls:
                    return
            stop_message = AssistantMessage(f"Stopped after {self.max_steps} steps without an answer.")
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


def skip_tool_call(call: ToolCall) -> QueryResult | InvalidCall:
    """Answer one of the model's tool calls without running it, after an interrupt.

    Every tool call needs an answer, or the API rejects the history.
    """
    try:
        args = parse_arguments(call.name, call.arguments)
    except InvalidToolCall as e:
        return InvalidCall(call.id, str(e))
    at = datetime.now(UTC)
    run = QueryRun(description=args.description, sql=args.sql, spec=args.spec, at=at, result=None, error="Canceled.")
    return QueryResult(call.id, run)
