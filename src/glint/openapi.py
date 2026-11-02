"""Print the API's OpenAPI schema, which the frontend's types are generated from."""

import json

from glint.server import create_app

if __name__ == "__main__":
    # The schema depends only on the routes, so no session, token or port is needed.
    print(json.dumps(create_app(session=None, token="", port=0).openapi(), indent=2))
