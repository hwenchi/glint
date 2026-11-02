"""The entries of a session's history, and their translation to and from the API."""

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from openai.types.chat import ChatCompletionMessage
from pydantic import Field

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
            return {"role": "tool", "tool_call_id": tool_call_id, "content": f"error: {error}"}


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
