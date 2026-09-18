"""Assistant web tools: fetch_url streaming, SSRF guard, charset and size limits."""
import httpx
import pytest

from quodeq.assistant.tools import _web_tools
from quodeq.assistant.tools._registry import ToolError


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


def test_fetch_url_invalid_url_is_tool_error(no_ssrf, monkeypatch):
    # httpx.InvalidURL is NOT an HTTPError subclass; it must still surface
    # as a readable ToolError, not dispatch's "failed internally"
    def boom(method, url, **kwargs):
        raise httpx.InvalidURL("Invalid non-printable ASCII character in URL")

    monkeypatch.setattr(httpx, "stream", boom)
    with pytest.raises(ToolError, match="could not fetch"):
        _web_tools._fetch_url("https://example.com/\tweird")


def test_fetch_url_binary_content_rejected_before_body_read(no_ssrf, monkeypatch):
    resp = _FakeStreamResponse(headers={"content-type": "image/png"}, body=b"\x89PNG")

    def explode(*args, **kwargs):
        raise AssertionError("body must not be read for binary content")

    resp.iter_bytes = explode
    monkeypatch.setattr(httpx, "stream", _fake_stream(resp))
    with pytest.raises(ToolError, match="content type"):
        _web_tools._fetch_url("https://example.com/logo.png")
