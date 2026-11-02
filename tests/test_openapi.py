import json
from pathlib import Path

from glint.server import create_app

COMMITTED = Path(__file__).parent.parent / "frontend" / "openapi.json"


def test_frontend_schema_is_current():
    # The frontend's types are generated from this file, so it must match the server.
    current = create_app(session=None, token="", port=0).openapi()
    assert current == json.loads(COMMITTED.read_text()), "the API changed: run make types"
