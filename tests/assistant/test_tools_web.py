import httpx
import pytest

from quodeq.assistant.tools import _web_tools
from quodeq.assistant.tools._registry import ToolError

_DDG_HTML = """
<html><body>
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fguide&amp;rut=abc">Example <b>guide</b></a>
  </h2>
  <a class="result__snippet" href="#">A useful <b>guide</b> to things.</a>
</div>
<div class="result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://plain.example.org/page">Plain link</a>
  </h2>
  <a class="result__snippet" href="#">Second snippet.</a>
</div>
</body></html>
"""


def _fake_get(status=200, text=_DDG_HTML):
    def fake(url, **kwargs):
        return httpx.Response(status, text=text, request=httpx.Request("GET", url))
    return fake


def test_search_web_parses_titles_urls_snippets(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get())
    out = _web_tools._search_web("stuff")
    assert out["results"][0] == {"title": "Example guide",
                                 "url": "https://example.com/guide",
                                 "snippet": "A useful guide to things."}
    assert out["results"][1]["url"] == "https://plain.example.org/page"


def test_search_web_caps_max_results(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get())
    assert len(_web_tools._search_web("stuff", max_results=1)["results"]) == 1


def test_search_web_http_error_is_tool_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(status=503))
    with pytest.raises(ToolError, match="503"):
        _web_tools._search_web("stuff")


def test_search_web_empty_page_is_tool_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(text="<html><body></body></html>"))
    with pytest.raises(ToolError, match="no results"):
        _web_tools._search_web("stuff")


def test_search_web_rejects_empty_query():
    with pytest.raises(ToolError, match="query"):
        _web_tools._search_web("  ")
