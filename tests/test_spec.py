import pytest

from glint.engine import Result
from glint.spec import InvalidSpec, snapshot

RESULT = Result(["rating", "n"], [("G", 178), ("PG", 194)])
BAR = {
    "mark": "bar",
    "encoding": {
        "x": {"field": "rating", "type": "nominal"},
        "y": {"field": "n", "type": "quantitative"},
    },
}


def test_snapshot():
    assert snapshot(BAR, RESULT) == {
        **BAR,
        "data": {"values": [{"rating": "G", "n": 178}, {"rating": "PG", "n": 194}]},
    }


def test_snapshot_replaces_data():
    spec = {**BAR, "data": {"url": "https://example.com/data.json"}}
    assert snapshot(spec, RESULT)["data"] == snapshot(BAR, RESULT)["data"]


def test_snapshot_leaves_spec_unchanged():
    spec = {**BAR}
    snapshot(spec, RESULT)
    assert spec == BAR


@pytest.mark.parametrize(
    "spec, message",
    [
        ({**BAR, "mark": "bars"}, "$.mark: 'bars' is not valid under any of the given schemas"),
        (
            {**BAR, "encoding": {"x": {"field": "rating", "type": "categorical"}}},
            "$.encoding.x.type: 'categorical' is not valid under any of the given schemas",
        ),
    ],
)
def test_invalid(spec, message):
    with pytest.raises(InvalidSpec) as e:
        snapshot(spec, RESULT)
    assert str(e.value) == message


def test_invalid_message_has_no_rows():
    result = Result(["secret"], [("do-not-leak",)])
    with pytest.raises(InvalidSpec) as e:
        snapshot({"mark": "bar", "encodings": {}}, result)
    assert "encodings" in str(e.value)
    assert "do-not-leak" not in str(e.value)
