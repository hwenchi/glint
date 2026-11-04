# Glint

> As you travel across the open ocean, your gaze drifts over its restless, heaving expanse. Light breaks across the water in countless facets, each one flaring and gone before you can fix on it. Every so often, one tilts toward you at just the right angle, and for an instant, you glimpse a tiny piece of the sun.

## What is this

Glint lets you explore a PostgreSQL database by asking questions in plain language. A language model investigates by writing and running SQL queries, then presents results as tables and charts. Every step exposes its description, SQL, and results.

Glint supports any model with tool calling through an OpenAI-compatible API, including local models served by Ollama.

## Why

An agent can work without supervision, but its judgment cannot be trusted to keep its actions safe. Human review, or review by another model, is no guarantee either. Judgment can guide a search; safety needs stronger guarantees.

Glint gets those guarantees by restricting what the agent can do. Database exploration is a good fit: each query returns a result that informs the next, and progress requires only reading data. The model has freedom to choose what to investigate, but no authority to modify the database.

Glint is not a general-purpose agent: it has no shell, filesystem or other tools. The model can act only through SQL queries, which read the database, and Vega-Lite specifications, which draw charts. Everything else it writes is shown to you as text.

Before a query runs, Glint analyzes its possible effects and rejects anything the config does not allow. By default, only reads are permitted. Unrecognized constructs count as effects; database definitions, such as views, are trusted. Queries run in a read-only transaction, so no action requires approval.

The safeguards are deliberately small:

- **Read-only:** One `SELECT`, checked by effect analysis and executed in a rolled-back, read-only transaction.
- **Bounded:** Query timeouts, a row limit that fails rather than truncates, one query at a time, and a step limit per message.
- **Private:** Charts are specifications, not scripts. Links are text; the page cannot contact other sites. Results go only to the configured model.
- **Local:** Bound to `127.0.0.1`, protected by a token and `Host` and `Origin` checks. History stays in memory or a private file.

A query can still consume resources or produce misleading results. Findings are hypotheses, not conclusions. Every chart includes the SQL and result table behind it, so you can inspect the evidence yourself.

## Run

Copy `glint.example.toml` to `glint.toml`, configure your database and an OpenAI-compatible model API, then run `make`.

`make dev` uses a sample database and local Ollama model. `make test` runs the tests.
