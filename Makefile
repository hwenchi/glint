PAGILA_URL := https://raw.githubusercontent.com/devrimgunduz/pagila/ce6e114236bb828e5ec0dc835f65f1bf1b9179f5
PAGILA := tests/db/initdb/01-pagila-schema.sql tests/db/initdb/02-pagila-data.sql

COMPOSE := docker compose -f tests/db/compose.yaml

# Read by compose for the host port, and by the tests to connect.
export GLINT_TEST_DB_PORT ?= 15432
export GLINT_TEST_DATABASE_URL := postgresql://postgres:postgres@127.0.0.1:$(GLINT_TEST_DB_PORT)/pagila

.PHONY: test image pagila db db-down db-reset

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
