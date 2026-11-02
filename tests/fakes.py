import json

import httpx2
from openai import OpenAI

from glint.engine import Result
from glint.history import AssistantMessage, to_api

RESULT = Result(["rating", "n"], [("G", 178)])


class FakeEndpoint:
    """An OpenAI-compatible endpoint that replays scripted assistant messages.

    The real client talks to it through httpx2's MockTransport, so requests and
    replies go through the SDK as they would over the network. The last reply
    repeats once the others are used up.
    """

    def __init__(self, *replies: AssistantMessage):
        self.replies = list(replies)
        self.requests = []

    def client(self):
        transport = httpx2.MockTransport(self._handle)
        return OpenAI(base_url="http://fake/v1", api_key="fake", http_client=httpx2.Client(transport=transport))

    def _handle(self, request):
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return httpx2.Response(200, json={
            "id": "fake",
            "object": "chat.completion",
            "created": 0,
            "model": "fake",
            "choices": [{
                "index": 0,
                "finish_reason": "tool_calls" if reply.tool_calls else "stop",
                "message": to_api(reply),
            }],
        })


class FakeEngine:
    """An Engine that returns a fixed result or error, and records the queries it gets."""

    def __init__(self, result=RESULT, error=None):
        self.result = result
        self.error = error
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if self.error:
            raise self.error
        return self.result
