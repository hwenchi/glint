import json

import pytest
from fastapi.testclient import TestClient

from fakes import FakeEndpoint, FakeEngine
from glint.agent import Session
from glint.history import AssistantMessage, History
from glint.server import CSP, TOKEN_COOKIE, create_app

TOKEN = "secret-token"
PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def session():
    endpoint = FakeEndpoint(AssistantMessage("Hello."))
    return Session(endpoint.client(), "fake-model", FakeEngine(), History())


@pytest.fixture
def client(session):
    app = create_app(session, TOKEN, PORT)
    app.get("/ping")(lambda: "pong")
    app.post("/ping")(lambda: "pong")
    return TestClient(app, base_url=ORIGIN, follow_redirects=False)


@pytest.fixture
def logged_in(client):
    client.cookies.set(TOKEN_COOKIE, TOKEN)
    return client


def test_token_becomes_cookie(client):
    response = client.get("/ping?token=secret-token&x=1")
    assert response.status_code == 303
    assert response.headers["location"] == f"{ORIGIN}/ping?x=1"
    cookie = response.headers["set-cookie"]
    assert f"{TOKEN_COOKIE}={TOKEN}" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_cookie_lets_in(logged_in):
    assert logged_in.get("/ping").status_code == 200


@pytest.mark.parametrize("path", ["/ping", "/ping?token=wrong", "/ping?token=ünïcode"])
def test_without_valid_token(client, path):
    assert client.get(path).status_code == 403


def test_wrong_cookie(client):
    client.cookies.set(TOKEN_COOKIE, "wrong")
    assert client.get("/ping").status_code == 403


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "192.168.1.5"])
def test_other_hosts(logged_in, host):
    assert logged_in.get("/ping", headers={"host": host}).status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765"])
def test_local_hosts(logged_in, host):
    assert logged_in.get("/ping", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("origin", [ORIGIN, f"http://localhost:{PORT}"])
def test_post_from_the_page(logged_in, origin):
    assert logged_in.post("/ping", headers={"origin": origin}).status_code == 200


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://127.0.0.1:9999"])
def test_post_from_elsewhere(logged_in, origin):
    headers = {"origin": origin} if origin else {}
    assert logged_in.post("/ping", headers=headers).status_code == 403


def test_security_headers(logged_in):
    headers = logged_in.get("/api/history").headers
    assert headers["content-security-policy"] == CSP
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["referrer-policy"] == "no-referrer"


def test_history_starts_empty(logged_in):
    assert logged_in.get("/api/history").json() == []


def test_message_streams_the_turn(logged_in):
    response = logged_in.post("/api/history", json={"text": "Hi"}, headers={"origin": ORIGIN})
    assert response.headers["content-type"].startswith("text/event-stream")
    events = response.text.split("\n\n")[:-1]  # each event ends with a blank line
    assert all(event.startswith("data: ") for event in events)
    entries = [json.loads(event.removeprefix("data: ")) for event in events]
    assert entries == [
        {"kind": "user", "text": "Hi"},
        {"kind": "assistant", "text": "Hello.", "tool_calls": []},
    ]
    assert logged_in.get("/api/history").json() == entries


def test_interrupt(logged_in, session, monkeypatch):
    calls = []
    monkeypatch.setattr(session, "interrupt", lambda: calls.append("interrupt"))
    response = logged_in.post("/api/interrupt", headers={"origin": ORIGIN})
    assert response.status_code == 204
    assert calls == ["interrupt"]
