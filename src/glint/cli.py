"""The glint command: start a session and serve it on localhost."""

import argparse
import secrets
import socket
import sys
import textwrap
import webbrowser
from datetime import timedelta
from pathlib import Path

import psycopg
import uvicorn
from openai import OpenAI
from pydantic import ValidationError

from glint.agent import Session
from glint.config import load_config
from glint.history import AssistantMessage, History, InvalidCall, QueryResult
from glint.postgres.engine import PostgresEngine
from glint.server import STATIC, create_app

MAX_ROWS = 500
TIMEOUT = timedelta(seconds=30)
# The values the pinned client's ReasoningEffort allows.
REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explore a PostgreSQL database with a language model.")
    parser.add_argument("config", nargs="?", type=Path, default=Path("glint.toml"), help="the config file")
    parser.add_argument("--history", type=Path, help="the file to keep the conversation in, instead of the config's")
    parser.add_argument("--model", help="the model to use, instead of the config's")
    parser.add_argument("--max-steps", type=int, help="model requests per user message, instead of the config's")
    parser.add_argument(
        "--reasoning-effort", choices=REASONING_EFFORTS, help="the request's reasoning_effort, instead of the config's"
    )
    parser.add_argument("--prompt", help="send this message, print the turn to the terminal, and exit")
    parser.add_argument("--list-models", action="store_true", help="print the models the config's endpoint offers, and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = args.config
    headless = args.prompt is not None  # print one turn to the terminal instead of serving the page
    serving = not headless and not args.list_models
    page_built = (STATIC / "index.html").exists()
    if serving and not page_built:
        sys.exit("The page isn't built: run make build.")
    try:
        config = load_config(path)
    except FileNotFoundError:
        sys.exit(f"No config at {path}: copy glint.example.toml to glint.toml and fill it in.")
    except ValidationError as e:
        sys.exit(f"Invalid config in {path}:\n{e}")
    client = OpenAI(base_url=config.model.base_url, api_key=config.model.api_key)
    if args.list_models:
        list_models(client)
        return
    history_path = args.history or config.history
    try:
        history = History(history_path)
    except (OSError, ValidationError) as e:
        sys.exit(f"Can't read the history in {history_path}:\n{e}")
    try:
        conn = psycopg.connect(config.database.connection)
    except psycopg.OperationalError as e:
        sys.exit(f"Can't connect to the database: {e}")

    engine = PostgresEngine(conn, config.effects.allow, MAX_ROWS, TIMEOUT)
    model = args.model or config.model.name
    max_steps = args.max_steps if args.max_steps is not None else config.model.max_steps
    reasoning_effort = args.reasoning_effort or config.model.reasoning_effort
    session = Session(client, model, engine, history, config.model.recent_results, max_steps, reasoning_effort)
    if headless:
        run_headless(session, args.prompt)
    else:
        serve(session)


def serve(session: Session) -> None:
    """Serve the session's page on localhost and open it in the browser."""
    # Bind first so the OS picks a free port, which the app needs for its origin check.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    app = create_app(session, token, port)

    url = f"http://127.0.0.1:{port}/chat/?token={token}"
    print(f"Glint is running at {url}", flush=True)
    webbrowser.open(url)
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


def run_headless(session: Session, prompt: str) -> None:
    """Send one message and print the turn to the terminal as it runs."""
    calls = 0
    failed = 0
    prompt_tokens = 0
    completion_tokens = 0
    try:
        for entry in session.respond(prompt):
            match entry:
                case AssistantMessage(text=text, usage=usage):
                    if text and text.strip():  # a reply that only calls the tool has none
                        print(text.strip(), flush=True)
                    if usage:
                        prompt_tokens += usage.prompt_tokens
                        completion_tokens += usage.completion_tokens
                case QueryResult(run=run):
                    calls += 1
                    if run.error:
                        failed += 1
                        print(f"[{calls}] error: {run.description}", flush=True)
                        print(textwrap.indent(run.error, "    "), flush=True)
                    else:
                        kind = "chart" if run.spec else "ok"
                        print(f"[{calls}] {kind}, {len(run.result.rows)} rows: {run.description}", flush=True)
                case InvalidCall(error=error):
                    calls += 1
                    failed += 1
                    print(f"[{calls}] invalid: {error}", flush=True)
    except KeyboardInterrupt:
        print("Interrupted.", flush=True)
    print(f"Tool calls: {calls}, {failed} failed. Tokens: {prompt_tokens:,} prompt, {completion_tokens:,} completion.")


def list_models(client: OpenAI) -> None:
    """Print the models the endpoint offers, one per line."""
    for id in sorted(m.id for m in client.models.list()):
        print(id)
