# Glint

> As you travel across the open ocean, your gaze drifts over its restless, heaving expanse. Light breaks across the water in countless facets, each one flaring and fading before you can fix on it. Every so often, one catches the light at just the right angle, and for an instant, you glimpse a tiny piece of the sun.

## What is Glint?

Glint lets you explore PostgreSQL databases using natural language. A language model investigates your data through SQL and presents its findings as tables and charts. Each step shows the SQL it ran and the results it received.

Glint takes a deliberately restrictive approach to building agents. Rather than assuming an agent should have access to tools, resources, and context, we start by giving it nothing and add only what its task requires. In Glint, the database is the agent's only external resource. It has no other tools, no files, and no access to its full conversation history. Its memory is limited to a small window of recent steps and a set of beliefs summarizing what it has learned.

## Safety

The agent can query the database but cannot modify it.

Before execution, each query is checked to reject operations other than reads. Queries run in a read-only transaction that is rolled back afterward. Execution timeouts and row limits bound individual queries, while a step limit bounds each investigation.

## Memory

The model receives two forms of memory:

- **Recent steps:** A rolling window of recent messages, queries, and results.
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
