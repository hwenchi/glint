import os

import psycopg
import pytest


@pytest.fixture
def conn():
    url = os.environ.get("GLINT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("no test database: run the tests with `make test`")
    with psycopg.connect(url) as conn:
        yield conn
