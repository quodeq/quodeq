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


class _FakeStreamResponse:
    def __init__(self, status=200, headers=None, body=b"", encoding="utf-8"):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.encoding = encoding

    def iter_bytes(self):
        yield self._body


class _FakeStream:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *args):
        return False


@pytest.fixture()
def no_ssrf(monkeypatch):
    # behavior tests must not resolve DNS; the SSRF path is tested separately
    # below with IP literals (which never hit the network)
    monkeypatch.setattr(_web_tools, "validate_url_safe", lambda url, **kw: None)


def _fake_stream(resp):
    def fake(method, url, **kwargs):
        assert kwargs.get("follow_redirects") is False
        return _FakeStream(resp)
    return fake


def test_fetch_url_rejects_private_addresses():
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest",
                "http://192.168.1.10/", "file:///etc/passwd"):
        with pytest.raises(ToolError):
            _web_tools._fetch_url(url)


def test_fetch_url_returns_redirect_without_following(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(status=302, headers={"location": "https://other.example/x"})
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert out["redirect_to"] == "https://other.example/x"
    assert "text" not in out


def test_fetch_url_extracts_text_and_strips_script(no_ssrf, monkeypatch):
    html = b"<html><head><title>T</title></head><body><script>evil()</script><p>Hello <b>world</b></p></body></html>"
    resp = _FakeStreamResponse(headers={"content-type": "text/html; charset=utf-8"}, body=html)
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert "Hello world" in out["text"]
    assert "evil" not in out["text"]


def test_fetch_url_truncates_long_text(no_ssrf, monkeypatch):
    body = b"<html><body><p>" + b"a" * 20_000 + b"</p></body></html>"
    resp = _FakeStreamResponse(headers={"content-type": "text/html"}, body=body)
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert out["truncated"] is True
    assert len(out["text"]) <= _web_tools._MAX_TEXT_CHARS


def test_fetch_url_http_status_error(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(status=404)
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    with pytest.raises(ToolError, match="404"):
        _web_tools._fetch_url("https://example.com/missing")


def test_fetch_url_network_error_is_tool_error(no_ssrf, monkeypatch):
    def boom(method, url, **kwargs):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "stream", boom)
    with pytest.raises(ToolError, match="refused"):
        _web_tools._fetch_url("https://example.com/a")


def test_fetch_url_rejects_binary_content(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(headers={"content-type": "image/png"}, body=b"\x89PNG")
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    with pytest.raises(ToolError, match="content type"):
        _web_tools._fetch_url("https://example.com/logo.png")


from pathlib import Path

from quodeq.assistant.tools import ToolContext, build_registry, register_web_tools
from quodeq.data.sqlite.assistant_repository import AssistantRepository
import quodeq.assistant.mcp.server as mcp_server


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
