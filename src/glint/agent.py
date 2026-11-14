"""The agent loop: the model queries and revises its beliefs until it answers."""

import threading
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
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
        recent_steps: int = 10,
        reasoning_effort: ReasoningEffort = None,
    ):
        self.client = client
        self.model = model
        self.engine = engine
        self._history = history
        self.beliefs = Beliefs(history.entries)
        # Short-term memory: the last few steps, oldest first. The oldest leaves as a new one comes in.
        self._recent: deque[list[Entry]] = deque(maxlen=recent_steps)
        # Steps since the beliefs were last revised. At recent_steps, they're revised.
        self._since_revision = 0
        for entry in history.entries:
            self._remember(entry)
        self.recent_steps = recent_steps
        self.max_steps = max_steps  # model requests per user message
        self.reasoning_effort = reasoning_effort  # sent only when set
        self.system_message = {"role": "system", "content": system_prompt(max_steps, max_beliefs, recent_steps)}
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
        self._history.extend(*entries)
        for entry in entries:
            self._remember(entry)

    def _remember(self, entry: Entry) -> None:
        """Add the entry to short-term memory: a user's message or a reply starts a step, and a result joins its reply's."""
        match entry:
            case UserMessage() | AssistantMessage():
                self._recent.append([entry])
                self._since_revision += 1
            case QueryResult() | InvalidCall():
                self._recent[-1].append(entry)
            case BeliefRevision():
                self._since_revision = 0

    def _revise_beliefs(self, reply: AssistantMessage) -> BeliefRevision:
        """Apply the reply's calls to revise_beliefs, as one revision, and return it.

        Raises InvalidToolCall if a call's arguments don't fit the tool, and ValueError
        if it drops a belief the model doesn't hold. Either way, nothing changes.
        """
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

        Each step, the model sees its beliefs and its last few steps, and:
        - every recent_steps steps, revises its beliefs, taking in what it sees;
        - otherwise queries, gathering evidence, or answers the user, which ends the turn.

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
                    interrupted = AssistantMessage("Interrupted.")
                    self._record(interrupted)
                    yield interrupted
                    return
                # The last step must answer, so its request offers no tool.
                last = step == self.max_steps - 1
                revising = self._since_revision >= self.recent_steps and not last
                context = context_message(self.beliefs.current, [entry for step in self._recent for entry in step])
                if last:
                    context += "\n\n" + LAST_STEP_NOTE
                    tools, tool_choice = NOT_GIVEN, NOT_GIVEN
                elif revising:
                    tools, tool_choice = [REVISE_BELIEFS_TOOL], "required"
                else:
                    tools, tool_choice = [QUERY_TOOL], NOT_GIVEN
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[self.system_message, {"role": "user", "content": context}],
                    tools=tools,
                    tool_choice=tool_choice,
                    reasoning_effort=self.reasoning_effort or NOT_GIVEN,
                )
                reply = from_api(response.choices[0].message, self.model, response.usage)
                if revising:
                    # The reply is recorded as the revision it makes, not as a step.
                    if not reply.tool_calls:
                        failed = AssistantMessage("Stopped: the model didn't revise its beliefs.")
                        self._record(failed)
                        yield failed
                        return
                    try:
                        revision = self._revise_beliefs(reply)
                    except (InvalidToolCall, ValueError) as e:
                        failed = AssistantMessage(f"Stopped: the model's revision of its beliefs was invalid. {e}")
                        self._record(failed)
                        yield failed
                        return
                    self._record(revision)
                    yield revision
                else:
                    self._record(reply)
                    yield reply
                    results = []
                    for call in reply.tool_calls:
                        # A model may call a tool even when none is offered; on the last step, such calls are skipped.
                        if self._interrupted.is_set() or last:
                            results.append(skip_tool_call(call))
                        else:
                            results.append(run_tool_call(self.engine, call))
                    self._record(*results)
                    yield from results
                    if not reply.tool_calls:
                        return
            stop_message = AssistantMessage(f"Stopped after {self.max_steps} steps without an answer.")
            self._record(stop_message)
            yield stop_message


def context_message(beliefs: Mapping[int, str], recent: Sequence[Entry]) -> str:
    """Glint's message to the model, in place of the conversation: its beliefs, numbered, and its last few steps."""
    beliefs_text = "\n".join(f"{number}. {statement}" for number, statement in beliefs.items()) or "Nothing yet."
    recent_text = "\n\n".join(describe(entry) for entry in recent)
    return f"Here is what you believe about the world:\n{beliefs_text}\n\nAnd what happened recently:\n\n{recent_text}"


def describe(entry: Entry) -> str:
    """An entry as plain text, as evidence for revising beliefs."""
    match entry:
        case UserMessage(text):
            return f"The user wrote:\n{text}"
        case AssistantMessage(text) if text:
            return f"You replied:\n{text}"
        case AssistantMessage():
            return "You replied by running queries."
        case QueryResult(_, run) if run.result is not None:
            return f"You ran a query: {run.description}\n{run.sql}\nResult: {run.result.model_dump_json()}"
        case QueryResult(_, run):
            return f"You ran a query: {run.description}\n{run.sql}\nError: {run.error}"
        case InvalidCall(_, error):
            return f"Your query couldn't be run: {error}"


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
