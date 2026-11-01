import pytest

from glint.spec import UrlNotAllowed, reject_urls


@pytest.mark.parametrize(
    "spec",
    [
        {"mark": "bar", "encoding": {"x": {"field": "rating", "type": "nominal"}}},
        # Only network requests are rejected; a chart that won't render, or
        # plots its own data, is for the model and the human to judge.
        {"mark": "bars", "encoding": {"x": {"field": "nope"}}},
        {"data": {"values": [{"rating": "G"}]}},
        {"mark": "image"},
        {"encoding": {"tooltip": {"field": "url"}}},
    ],
)
def test_allowed(spec):
    reject_urls(spec)


@pytest.mark.parametrize(
    "spec, path",
    [
        ({"data": {"url": "https://example.com/d.json"}}, "$.data.url"),
        ({"layer": [{}, {"data": {"url": "x"}}]}, "$.layer[1].data.url"),
        ({"transform": [{"lookup": "a", "from": {"data": {"url": "x"}}}]}, "$.transform[0].from.data.url"),
        ({"encoding": {"url": {"field": "image"}}}, "$.encoding.url"),
        ({"mark": {"type": "image", "url": "https://example.com/i.png"}}, "$.mark.url"),
        ({"encoding": {"href": {"field": "rating"}}}, "$.encoding.href"),
        ({"mark": {"type": "bar", "href": "https://example.com"}}, "$.mark.href"),
        ({"config": {"mark": {"href": "https://example.com"}}}, "$.config.mark.href"),
        ({"vconcat": [{"hconcat": [{"encoding": {"href": {"field": "x"}}}]}]}, "$.vconcat[0].hconcat[0].encoding.href"),
    ],
)
def test_rejected(spec, path):
    with pytest.raises(UrlNotAllowed) as e:
        reject_urls(spec)
    assert str(e.value).startswith(f"{path}:")
