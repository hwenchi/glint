"""The glint command: start a session and serve it on localhost."""

import secrets
import socket
import sys
import webbrowser
from datetime import timedelta
from pathlib import Path

import psycopg
import uvicorn
from openai import OpenAI
from pydantic import ValidationError

from glint.agent import Session
from glint.config import load_config
from glint.history import History
from glint.postgres.engine import PostgresEngine
from glint.server import STATIC, create_app

MAX_ROWS = 500
TIMEOUT = timedelta(seconds=30)


def main() -> None:
    if not (STATIC / "index.html").exists():
        sys.exit("The page isn't built: run make build.")
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "glint.toml")
    try:
        config = load_config(path)
    except FileNotFoundError:
        sys.exit(f"No config at {path}: copy glint.example.toml to glint.toml and fill it in.")
    except ValidationError as e:
        sys.exit(f"Invalid config in {path}:\n{e}")
    try:
        history = History(config.history)
    except (OSError, ValidationError) as e:
        sys.exit(f"Can't read the history in {config.history}:\n{e}")
    try:
        conn = psycopg.connect(config.database.connection)
    except psycopg.OperationalError as e:
        sys.exit(f"Can't connect to the database: {e}")

    engine = PostgresEngine(conn, config.effects.allow, MAX_ROWS, TIMEOUT)
    client = OpenAI(base_url=config.model.base_url, api_key=config.model.api_key)
    session = Session(
        client, config.model.name, engine, history, config.model.recent_results, config.model.max_steps
    )

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
