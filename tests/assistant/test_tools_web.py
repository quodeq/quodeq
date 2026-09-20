"""Assistant web tools: search_web parsing and web-tool registry gating."""
from pathlib import Path

import httpx
import pytest

import quodeq.assistant.mcp.server as mcp_server
from quodeq.assistant.tools import ToolContext, _web_tools, build_registry, register_web_tools
from quodeq.assistant.tools.registry import ToolError
from quodeq.data.sqlite.assistant_repository import AssistantRepository


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


_MANY_RESULTS_HTML = "<html><body>" + "".join(
    f'<div class="result"><h2 class="result__title">'
    f'<a class="result__a" href="https://example.org/{i}">R{i}</a></h2>'
    f'<a class="result__snippet" href="#">s{i}</a></div>'
    for i in range(10)
) + "</body></html>"


def test_search_web_clamps_oversized_max_results(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(text=_MANY_RESULTS_HTML))
    out = _web_tools._search_web("stuff", max_results=99)
    assert len(out["results"]) == 8


def test_search_web_non_numeric_max_results_is_tool_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get())
    with pytest.raises(ToolError, match="max_results"):
        _web_tools._search_web("stuff", max_results="abc")


_HOSTILE_DDG_HTML = """
<html><body>
<div class="result"><h2 class="result__title">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=javascript%3Aalert(1)&amp;rut=x">Evil</a>
</h2><a class="result__snippet" href="#">bad</a></div>
<div class="result"><h2 class="result__title">
  <a class="result__a" href="/relative/path">Relative</a>
</h2><a class="result__snippet" href="#">also bad</a></div>
<div class="result"><h2 class="result__title">
  <a class="result__a" href="https://good.example.com/">Good</a>
</h2><a class="result__snippet" href="#">fine</a></div>
</body></html>
"""


def test_search_web_filters_non_http_result_urls(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(text=_HOSTILE_DDG_HTML))
    out = _web_tools._search_web("stuff")
    assert [r["url"] for r in out["results"]] == ["https://good.example.com/"]


_LONG_TITLE_HTML = ('<html><body><div class="result"><h2 class="result__title">'
                    '<a class="result__a" href="https://example.org/long">'
                    + "T" * 400 +
                    '</a></h2><a class="result__snippet" href="#">s</a></div>'
                    '</body></html>')


def test_search_web_caps_title_length(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(text=_LONG_TITLE_HTML))
    out = _web_tools._search_web("stuff")
    assert len(out["results"][0]["title"]) <= 300


@pytest.fixture()
def ctx(tmp_path):
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(repository=repo, session_id="s1", run_dir=None, repo_root=None,
                       evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
                       dimensions_file=tmp_path / "d.json")


def test_build_registry_never_includes_web_tools(ctx):
    names = build_registry(ctx).names()
    assert "search_web" not in names and "fetch_url" not in names


def test_register_web_tools_adds_exactly_two(ctx):
    registry = build_registry(ctx)
    before = set(registry.names())
    register_web_tools(registry)
    assert set(registry.names()) - before == {"search_web", "fetch_url"}


def test_registered_web_tools_dispatch_and_fail_readably(ctx):
    registry = build_registry(ctx)
    register_web_tools(registry)
    out = registry.dispatch("fetch_url", {"url": "http://127.0.0.1/x"})
    assert out["ok"] is False
    assert "private" in out["error"]  # ToolError text, not "failed internally"


def test_mcp_server_module_never_references_web_tools():
    # THE invariant: web tools reaching the MCP server would give the claude
    # CLI web access with the toggle OFF (blanket --allowedTools on the server).
    source = Path(mcp_server.__file__).read_text(encoding="utf-8")
    assert "register_web_tools" not in source and "_web_tools" not in source
