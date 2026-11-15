# Glint

> As you travel across the open ocean, your gaze drifts over its restless, heaving expanse. Light breaks across the water in countless facets, each one flaring and fading before you can fix on it. Every so often, one catches the light at just the right angle, and for an instant, you glimpse a tiny piece of the sun.

## What is Glint?

Glint lets you explore PostgreSQL databases using natural language. A language model investigates your data through SQL and presents its findings as tables and charts. Each step shows the SQL it ran and the results it received.

Glint is built around a simple principle: an agent should have access only to what it needs, and retain only what matters. This principle shapes two aspects of its design: what the agent can access and what it remembers.

First, Glint takes a deliberately minimal approach to access. Rather than giving the agent a broad set of tools, resources, and context by default, we start with nothing and introduce only what the task requires. In Glint, the database is the agent's only external resource. It has no other tools, no files, and no access to its full conversation history.

Second, Glint takes a selective approach to memory. Human memory offers a useful analogy: unless we're deliberately trying to memorize something, we rarely remember the exact words spoken in a conversation. Instead, we retain what we understood from it. We build an understanding through experience, preserving what matters and revising it as we learn more. Glint follows a similar approach. Rather than retaining every detail of its interactions, it maintains an evolving understanding of the data—a set of beliefs that it updates as it investigates.

The agent's working context is intentionally limited, too: it can see only a small window of recent steps alongside these accumulated beliefs. This keeps its immediate context focused on the current task while allowing its understanding to develop over time.

## Safety

The agent can query the database but cannot modify it.

Before execution, each query is checked to reject operations other than reads. Queries run in a read-only transaction that is rolled back afterward. Execution timeouts and row limits bound individual queries, while a step limit bounds each investigation.

## Memory

The model receives two forms of memory:

- **Recent steps:** A deliberately small rolling window of recent messages, queries, and results.
- **Beliefs:** A concise summary of facts, relationships, and patterns learned during the investigation.

Every few steps, before older entries leave the window, the model reviews its beliefs, adding new findings, revising existing ones, and removing those it no longer considers valid. Each revision appears in the conversation.

The full transcript is retained for auditing, but is never passed to the model in full. The model sees only its beliefs, recent steps, and the request it is answering.

## Running Glint

Copy `glint.example.toml` to `glint.toml` and configure your PostgreSQL connection and an OpenAI-compatible model API that supports tool calling.

Run Glint:

```bash
make
```

Start the development setup:

```bash
make dev
```

Run the tests:

```bash
make test
```
