from glint.engine import Result

RESULT = Result(["rating", "n"], [("G", 178)])


class FakeEngine:
    """An Engine that returns a fixed result or error, and records the queries it gets."""

    def __init__(self, result=RESULT, error=None):
        self.result = result
        self.error = error
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if self.error:
            raise self.error
        return self.result
