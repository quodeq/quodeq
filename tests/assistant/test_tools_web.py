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


class _FakeStreamResponse:
    def __init__(self, status=200, headers=None, body=b"", encoding="utf-8",
                 chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.encoding = encoding
        self._chunks = chunks

    def iter_bytes(self, chunk_size=None):
        chunks = self._chunks if self._chunks is not None else [self._body]
        if chunk_size is None:
            yield from chunks
            return
        # mirror httpx's ByteChunker: buffer until chunk_size bytes accumulate,
        # so small network chunks do NOT reach the caller's loop individually
        buf = b""
        for chunk in chunks:
            buf += chunk
            while len(buf) >= chunk_size:
                yield buf[:chunk_size]
                buf = buf[chunk_size:]
        if buf:
            yield buf


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


def test_fetch_url_survives_unknown_charset(no_ssrf, monkeypatch):
    # charset=zlib_codec makes bytes.decode raise LookupError (not a text
    # encoding); the tool must fall back to utf-8, not crash the turn
    resp = _FakeStreamResponse(
        headers={"content-type": "text/html; charset=zlib_codec"},
        body=b"<p>hi</p>", encoding="zlib_codec")
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert "hi" in out["text"]


def test_fetch_url_content_type_case_insensitive(no_ssrf, monkeypatch):
    # RFC 2045: MIME types are case-insensitive; real servers send Text/HTML
    resp = _FakeStreamResponse(
        headers={"content-type": "Text/HTML; charset=utf-8"},
        body=b"<p>Hello <b>world</b></p>")
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert "Hello world" in out["text"]


def test_fetch_url_honors_declared_charset(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(
        headers={"content-type": "text/plain; charset=iso-8859-1"},
        body=b"caf\xe9", encoding="iso-8859-1")
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    assert _web_tools._fetch_url("https://example.com/a")["text"] == "café"


def test_fetch_url_redirect_without_location_header(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(status=301, headers={})
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert out["redirect_to"] == ""
    assert "text" not in out


def test_fetch_url_rejects_non_string_url():
    with pytest.raises(ToolError, match="string"):
        _web_tools._fetch_url(12345)


def test_fetch_url_byte_cap_sets_truncated(no_ssrf, monkeypatch):
    # 3 MB of markup whose extracted text is empty: the 2 MB byte cap was hit,
    # so truncated must be True even though the text itself is short
    body = b"<br>" * (3 * 1024 * 1024 // 4)
    resp = _FakeStreamResponse(headers={"content-type": "text/html"}, body=body)
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert out["truncated"] is True
    assert len(out["text"]) <= _web_tools._MAX_TEXT_CHARS


class _FakeClock:
    """monotonic() that jumps 30s per call: three loop checks blow a 60s budget."""

    def __init__(self, step=30.0):
        self._now = 0.0
        self._step = step

    def monotonic(self):
        self._now += self._step
        return self._now


def test_fetch_url_deadline_fires_on_slow_drip(no_ssrf, monkeypatch):
    # sub-64KB chunks must reach the loop individually so the deadline check
    # runs per chunk; a chunk_size= arg routes through httpx's ByteChunker,
    # which buffers them into one late chunk and lets a slow-drip server
    # wedge the turn thread past the budget
    resp = _FakeStreamResponse(headers={"content-type": "text/html"},
                               chunks=[b"a", b"b", b"c"])
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    monkeypatch.setattr(_web_tools, "time", _FakeClock())
    with pytest.raises(ToolError, match="time budget"):
        _web_tools._fetch_url("https://example.com/slow")


def test_fetch_url_keeps_trailing_text_near_bare_ampersand(no_ssrf, monkeypatch):
    # without extractor.close(), convert_charrefs buffers the trailing run
    # after a bare & and silently drops it
    resp = _FakeStreamResponse(headers={"content-type": "text/html"},
                               body=b"<p>Hello</p>ends with &am")
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    out = _web_tools._fetch_url("https://example.com/a")
    assert "ends with" in out["text"]


_LONG_TITLE_HTML = ('<html><body><div class="result"><h2 class="result__title">'
                    '<a class="result__a" href="https://example.org/long">'
                    + "T" * 400 +
                    '</a></h2><a class="result__snippet" href="#">s</a></div>'
                    '</body></html>')


def test_search_web_caps_title_length(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(text=_LONG_TITLE_HTML))
    out = _web_tools._search_web("stuff")
    assert len(out["results"][0]["title"]) <= 300


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
