"""The agent loop: the model queries and revises its beliefs until it answers."""

import threading
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from openai import NOT_GIVEN, OpenAI
from openai.types.shared import ReasoningEffort

from glint.beliefs import Beliefs
from glint.engine import Engine
from glint.history import (
    AssistantMessage,
    BeliefRevision,
    Entry,
    History,
    InvalidCall,
    QueryResult,
    ToolCall,
    UserMessage,
    from_api,
    in_conversation,
    to_api,
)
from glint.prompt import LAST_STEP_NOTE, system_prompt
from glint.tool import (
    QUERY_TOOL,
    REVISE_BELIEFS_TOOL,
    InvalidToolCall,
    QueryRun,
    parse_arguments,
    parse_revise_beliefs_arguments,
    run_query,
)


@dataclass
class Observation:
    """Where an observation is in the history: a reply with tool calls and their results."""

    start: int  # the reply's index
    end: int  # the index after its last result


class Session:
    """The one conversation of this Glint process. Only respond adds to its history."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        engine: Engine,
        history: History,
        max_steps: int = 100,
        max_beliefs: int = 50,
        max_observations: int = 10,
        reasoning_effort: ReasoningEffort = None,
    ):
        self.client = client
        self.model = model
        self.engine = engine
        self._history = history
        self.beliefs = Beliefs(history.entries)
        self.max_observations = max_observations
        # Short-term memory: the last few observations, oldest first.
        self._recent_observations: deque[Observation] = deque()
        # Observations since the beliefs were last revised. At max_observations, they're revised.
        self._new_observations = 0
        for index, entry in enumerate(history.entries):
            self._remember(index, entry)
        self.max_steps = max_steps  # model requests per user message
        self.reasoning_effort = reasoning_effort  # sent only when set
        self.system_message = {"role": "system", "content": system_prompt(max_steps, max_beliefs, max_observations)}
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

    def _record(self, *entries: Entry) -> None:
        """Add the entries to the history and to short-term memory."""
        start = len(self._history.entries)
        self._history.extend(*entries)
        for index, entry in enumerate(entries, start):
            self._remember(index, entry)

    def _remember(self, index: int, entry: Entry) -> None:
        """Add the history entry at index to short-term memory: a reply with tool calls starts an observation, and
        each result joins it."""
        match entry:
            case AssistantMessage(tool_calls=calls) if calls:
                self._recent_observations.append(Observation(index, index + 1))
                self._new_observations += 1
                # Short-term memory must keep:
                # - the last max_observations;
                # - every new observation, which the beliefs haven't taken in yet.
                # All older observations are forgotten.
                keep = max(self.max_observations, self._new_observations)
                while len(self._recent_observations) > keep:
                    self._recent_observations.popleft()
            case QueryResult() | InvalidCall():
                self._recent_observations[-1].end = index + 1
            case BeliefRevision():
                self._new_observations = 0

    def _memory(self) -> list[dict]:
        """The conversation and the recent observations, in the order they happened, as API messages."""
        observed = {index for observation in self._recent_observations for index in range(observation.start, observation.end)}
        return [
            to_api(entry)
            for index, entry in enumerate(self._history.entries)
            if in_conversation(entry) or index in observed
        ]

    def _revise_beliefs(self, reply: AssistantMessage) -> BeliefRevision:
        """Apply the reply's calls to revise_beliefs, as one revision, and return it.

        Raises InvalidToolCall if the reply has no call or a call's arguments don't fit the tool, and ValueError
        if it drops a belief the model doesn't hold. Either way, nothing changes.
        """
        if not reply.tool_calls:
            raise InvalidToolCall("Revise your beliefs with revise_beliefs.")
        drop: dict[int, str] = {}
        add: dict[int, str] = {}
        number = self.beliefs.next_number
        for call in reply.tool_calls:
            args = parse_revise_beliefs_arguments(call.name, call.arguments)
            for dropped in args.drop:
                drop[dropped] = self.beliefs.current.get(dropped, "")  # apply rejects any not held
            for statement in args.add:
                add[number] = statement
                number += 1
        revision = BeliefRevision(drop, add, reply.usage, reply.model)
        self.beliefs.apply(revision)
        return revision

    def respond(self, text: str) -> Iterator[Entry]:
        """Answer the user's message.

        Each step, the model sees its beliefs, the conversation, and its recent observations, and:
        - every max_observations observations, revises its beliefs;
        - otherwise queries, or answers the user, which ends the turn.

        Each new entry is added to the history and yielded, so it can be shown as it arrives.
        Turns don't overlap: a second one waits until the first has ended.
        """
        with self._turn:
            self._interrupted.clear()  # a stop sent between turns isn't for this one
            user_message = UserMessage(text)
            self._record(user_message)
            yield user_message
            for step in range(self.max_steps):
                if self._interrupted.is_set():
                    interrupted = AssistantMessage("Interrupted.", final=True)
                    self._record(interrupted)
                    yield interrupted
                    return
                # The last step must answer, so its request offers no tool.
                last = step == self.max_steps - 1
                revising = self._new_observations >= self.max_observations and not last
                beliefs = {"role": "user", "content": beliefs_message(self.beliefs.current)}
                messages = [self.system_message, beliefs, *self._memory()]
                if last:
                    # Not in the history: like the system prompt, it's Glint's, not the conversation's.
                    messages.append({"role": "user", "content": LAST_STEP_NOTE})
                    tools, tool_choice = NOT_GIVEN, NOT_GIVEN
                elif revising:
                    tools, tool_choice = [REVISE_BELIEFS_TOOL], "required"
                else:
                    tools, tool_choice = [QUERY_TOOL], NOT_GIVEN
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    reasoning_effort=self.reasoning_effort or NOT_GIVEN,
                )
                message = response.choices[0].message
                # An answer: no tool calls on a step that isn't a revision. It ends the turn.
                final = not revising and not message.tool_calls
                reply = from_api(message, self.model, response.usage, final)
                if revising:
                    try:
                        revision = self._revise_beliefs(reply)
                    except (InvalidToolCall, ValueError) as e:
                        # An observation, with an error for each call. The next step must revise again.
                        errors = [InvalidCall(call.id, f"Not applied: {e}") for call in reply.tool_calls]
                        self._record(reply, *errors)
                        yield reply
                        yield from errors
                        continue
                    # A valid revision is recorded as itself, not as an observation.
                    self._record(revision)
                    yield revision
                else:
                    results = []
                    for call in reply.tool_calls:
                        # A model may call a tool even when none is offered; on the last step, such calls are skipped.
                        if self._interrupted.is_set() or last:
                            results.append(skip_tool_call(call))
                        else:
                            results.append(run_tool_call(self.engine, call))
                    # Together: a call needs its result.
                    self._record(reply, *results)
                    yield reply
                    yield from results
                    if reply.final:
                        return
            stop_message = AssistantMessage(f"Stopped after {self.max_steps} steps without an answer.", final=True)
            self._record(stop_message)
            yield stop_message


def beliefs_message(beliefs: Mapping[int, str]) -> str:
    """Glint's message giving the model its beliefs, numbered."""
    beliefs_text = "\n".join(f"{number}. {statement}" for number, statement in beliefs.items()) or "Nothing yet."
    return f"Glint: Here is what you believe about the world:\n{beliefs_text}"


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
