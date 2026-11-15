# Glint

> As you travel across the open ocean, your gaze drifts over its restless, heaving expanse. Light breaks across the water in countless facets, each one flaring and fading before you can fix on it. Every so often, one catches the light at just the right angle, and for an instant, you glimpse a tiny piece of the sun.

## What is Glint?

Glint lets you explore PostgreSQL databases using natural language. An AI agent investigates your data by writing and executing SQL, then presents its findings as tables and charts.

Every step is visible: the SQL it ran and the results it received.

Glint is built around two principles: **minimal access and selective memory.**

### Minimal access

The database is the agent's only external resource. Glint deliberately gives the agent no other tools, file access, or external resources.

Its working context is also deliberately limited: it sees the conversation and a small rolling window of recent tool calls, including SQL queries and their results. Older tool calls are not passed to the model.

### Selective memory

Rather than retaining every query and result in its working context, Glint maintains an evolving set of beliefs about the data.

These beliefs capture useful facts, relationships, and patterns discovered during an investigation. As new evidence comes in, the agent can add to them, revise them, or discard them.

Every few steps, before older tool calls leave the working window, the model reviews and updates its beliefs. These updates are visible in the conversation.

The result is an agent that can build an understanding of your data without carrying the entire history of its investigation.

## Safety

Glint is read-only. The agent can query the database but cannot modify it.

Every query passes through a read-only check before execution. Queries run inside a read-only transaction that is rolled back afterward.

Execution timeouts and row limits constrain individual queries. A step limit constrains each investigation.

## Memory

The model receives two forms of context:

- **Recent tool calls:** A small rolling window of recent SQL queries and their results.
- **Beliefs:** An evolving summary of facts, relationships, and patterns learned from the data.

The full transcript, including conversation messages and tool calls, is retained for auditing. However, the model receives the conversation and accumulated beliefs alongside only a small window of recent tool calls—not the full history of tool calls.

## Running Glint

Copy the example configuration:

```sh
cp glint.example.toml glint.toml
```

Configure your PostgreSQL connection and an OpenAI-compatible model API that supports tool calling.

Run Glint:

```sh
make
```

Start the development setup:

```sh
make dev
```

Run the tests:

```sh
make test
```
