# Glint

*Find the insights hiding in your data.*

Ask questions about a PostgreSQL database in plain language. A language model writes the queries and charts; you see every query it runs.

## Why

An agent is only useful unsupervised, but its programs can't be trusted unread. Glint picks a task where nothing can have a lasting effect, exploring data, and a fixed harness enforces that, so nothing needs review and the model's quality only affects how much you gain.

- **Read-only:** one `SELECT` checked against an allowlist, run in a rolled-back read-only transaction.
- **Bounded:** timeouts, a row limit that fails rather than truncates, one query at a time.
- **No data leaves:** charts are data, never code; no URLs, no `eval`, a strict CSP.
- **Local only:** `127.0.0.1`, a token, `Host` and `Origin` checks, history in memory.

Findings are hypotheses: each chart shows its SQL and table so you can check it.

## Run

Copy `glint.example.toml` to `glint.toml`, fill in your database and an OpenAI-compatible model with tool calling, then run `make`.

`make dev` uses a sample database and a local Ollama model; `make test` runs the tests.
