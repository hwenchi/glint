PAGILA_URL := https://raw.githubusercontent.com/devrimgunduz/pagila/ce6e114236bb828e5ec0dc835f65f1bf1b9179f5
PAGILA := tests/db/initdb/01-pagila-schema.sql tests/db/initdb/02-pagila-data.sql

COMPOSE := docker compose -f tests/db/compose.yaml

# Read by compose for the host port, and by the tests to connect.
export GLINT_TEST_DB_PORT ?= 15432
export GLINT_TEST_DATABASE_URL := postgresql://postgres:postgres@127.0.0.1:$(GLINT_TEST_DB_PORT)/pagila

.PHONY: test image pagila db db-down db-reset types build run dev ollama schema
.DEFAULT_GOAL := run

# Glint with the database and model in glint.toml; see glint.example.toml.
run: build
	uv run glint glint.toml

# Glint on the test database with a local model from Ollama; see dev.toml.
dev: build db ollama
	uv run glint dev.toml

# Ollama running, started in the background if it isn't. The model in dev.toml
# must already be pulled: ollama pull qwen3.6:27b
ollama:
	ollama list > /dev/null 2>&1 || (ollama serve > /dev/null 2>&1 &)
	until ollama list > /dev/null 2>&1; do sleep 0.2; done

# The page, built into the Python package, which serves it.
build: types
	cd frontend && npm run build

# The Vega-Lite schema the server checks the model's charts against, from the
# version the page renders with. Committed, since the package needs it at runtime.
schema: frontend/node_modules
	cp frontend/node_modules/vega-lite/build/vega-lite-schema.json src/glint/schemas/vega-lite.json

# The frontend's API types, generated from the server's OpenAPI schema.
types: frontend/node_modules
	uv run python -m glint.openapi > frontend/openapi.json
	cd frontend && npm run types

# The frontend's packages, exactly as locked; reinstalled when the lockfile changes.
frontend/node_modules: frontend/package-lock.json
	cd frontend && npm ci
	touch $@

# Everything below is for testing.

test: db
	uv run pytest

# Test database, started if not running. Waits until the init scripts are done.
db: image pagila
	$(COMPOSE) up -d --wait

# Stop the test database, keeping its data.
db-down:
	$(COMPOSE) down

# Recreate the test database from scratch. The init scripts only run on an
# empty volume, so this is needed after changing them.
db-reset:
	$(COMPOSE) down -v
	$(MAKE) db

# Test database image: PostgreSQL 18 with pgvector.
image:
	docker build -t glint-test-db tests/db

# Sample data, downloaded once from a pinned commit.
pagila: $(PAGILA)

tests/db/initdb/01-pagila-schema.sql:
	curl -fsSL --create-dirs -o $@ $(PAGILA_URL)/pagila-schema.sql

tests/db/initdb/02-pagila-data.sql:
	curl -fsSL --create-dirs -o $@ $(PAGILA_URL)/pagila-data.sql
