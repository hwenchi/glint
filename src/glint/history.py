"""The entries of a session's history, and their translation to and from the API."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from openai.types.chat import ChatCompletionMessage
from pydantic import Field, TypeAdapter

from glint.tool import QueryRun


# Each entry's kind tags it in JSON, so the page can tell entries apart. It
# comes last, with a default, so constructors and match patterns ignore it.


@dataclass(frozen=True)
class UserMessage:
    text: str
    kind: Literal["user"] = "user"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON, as the model wrote it


@dataclass(frozen=True)
class AssistantMessage:
    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    kind: Literal["assistant"] = "assistant"


@dataclass(frozen=True)
class QueryResult:
    """The answer to a tool call that ran a query."""

    tool_call_id: str
    run: QueryRun
    kind: Literal["query_result"] = "query_result"


@dataclass(frozen=True)
class InvalidCall:
    """The answer to a tool call that couldn't be parsed."""

    tool_call_id: str
    error: str
    kind: Literal["invalid_call"] = "invalid_call"


Entry = Annotated[UserMessage | AssistantMessage | QueryResult | InvalidCall, Field(discriminator="kind")]

ENTRY = TypeAdapter(Entry)


class History:
    """A session's entries, saved to a file after every change if given one."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._entries = _load(path) if path else []

    @property
    def entries(self) -> Sequence[Entry]:
        return self._entries

    def extend(self, *entries: Entry) -> None:
        """Add the entries together, so the file never has a tool call without its result."""
        self._entries.extend(entries)
        if self.path:
            _save(self._entries, self.path)


def _save(entries: list[Entry], path: Path) -> None:
    """Write the entries to path, one per line, replacing the file whole so a crash never leaves half of one.

    Only the owner may read it: it holds query results.
    """
    temp = path.with_name(path.name + ".tmp")
    # Created private, so the data is never readable by others, not even briefly.
    with open(temp, "wb", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        os.fchmod(f.fileno(), 0o600)  # in case a leftover temp file had wider permissions
        f.writelines(ENTRY.dump_json(entry) + b"\n" for entry in entries)
    os.replace(temp, path)


def _load(path: Path) -> list[Entry]:
    """The entries saved at path, or none if nothing has been saved yet."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    return [ENTRY.validate_json(line) for line in data.splitlines()]


def to_api(entry: Entry) -> dict[str, Any]:
    """The entry as a message for the chat completions API, which is all the model sees."""
    match entry:
        case UserMessage(text):
            return {"role": "user", "content": text}
        case AssistantMessage(text, ()):
            return {"role": "assistant", "content": text}
        case AssistantMessage(text, tool_calls):
            return {
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in tool_calls
                ],
            }
        case QueryResult(tool_call_id, QueryRun(error=None, result=result)):
            return {"role": "tool", "tool_call_id": tool_call_id, "content": result.model_dump_json()}
        case QueryResult(tool_call_id, QueryRun(error=error)) | InvalidCall(tool_call_id, error):
            return {"role": "tool", "tool_call_id": tool_call_id, "content": f"Error: {error}"}


def to_api_messages(entries: Sequence[Entry], recent: int) -> list[dict[str, Any]]:
    """The entries as messages for the model, with the rows of all but the most recent results omitted.

    Errors are always sent in full, and don't count toward the recent results.
    """
    results = [i for i, e in enumerate(entries) if isinstance(e, QueryResult) and e.run.result is not None]
    first_included = max(len(results) - recent, 0)
    omitted = set(results[:first_included])
    return [to_api_omitted(e) if i in omitted else to_api(e) for i, e in enumerate(entries)]


def to_api_omitted(result: QueryResult) -> dict[str, Any]:
    """The result as a message without its rows, to save the model's context. The model can run the query again."""
    return {"role": "tool", "tool_call_id": result.tool_call_id, "content": "Omitted."}


def from_api(message: ChatCompletionMessage) -> AssistantMessage:
    """The model's reply as an entry."""
    tool_calls = []
    for call in message.tool_calls or ():
        match call.type:
            case "function":
                tool_calls.append(ToolCall(call.id, call.function.name, call.function.arguments))
            case "custom":
                # Only a function tool is offered; running this answers it with "unknown tool".
                tool_calls.append(ToolCall(call.id, call.custom.name, call.custom.input))
    return AssistantMessage(message.content, tuple(tool_calls))
