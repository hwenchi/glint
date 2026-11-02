# Glint

> As you travel across the open ocean, your gaze drifts over its restless, heaving expanse. Light breaks across the water in countless facets, each one flaring and gone before you can fix on it. Every so often, one tilts toward you at just the right angle, and for an instant, you glimpse a tiny piece of the sun.

Ask questions about a PostgreSQL database in plain language. A language model writes the queries and charts; you see every query it runs.

## Why

An agent is useful because it runs unsupervised, but its generated programs can't be trusted without being read, and reading them defeats the purpose. Glint avoids that by choosing a task where no action can have a lasting effect, so no action needs approval and the model's quality affects only how much you gain.

Data exploration fits: its output is a view, not a change, and finding insights is a search over queries that language models narrow well, so anyone can explore a database without programming or data-science skills.

- **Read-only:** one `SELECT` checked against an allowlist, run in a rolled-back read-only transaction.
- **Bounded:** timeouts, a row limit that fails rather than truncates, one query at a time, 20 steps per message.
- **No data leaves:** charts are data, never code; links shown as text; no URLs, no `eval`, a strict CSP; results go only to the model.
- **Local only:** `127.0.0.1`, a token, `Host` and `Origin` checks, history in memory or a private file.

Findings are hypotheses: each chart shows its SQL and table so you can check it.

## Run

Copy `glint.example.toml` to `glint.toml`, fill in your database and an OpenAI-compatible model with tool calling, then run `make`.

`make dev` uses a sample database and a local Ollama model; `make test` runs the tests.
