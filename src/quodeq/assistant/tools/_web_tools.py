"""Opt-in web tools for local providers: DuckDuckGo search + guarded URL fetch.

NEVER registered from build_registry(): the MCP server builds its registry
there, and web tools reaching the MCP server would hand the claude CLI web
access with the drawer toggle OFF (its --allowedTools blanket-allows every
tool on the quodeq-assistant server). register_web_tools() is called only
from the orchestrator's API branch, gated on web_enabled + LOCAL_PROVIDERS.
"""
from __future__ import annotations

import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.shared.url_validation import validate_url_safe

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
_MAX_RESULTS = 8
_MAX_FETCH_BYTES = 2 * 1024 * 1024
_MAX_FETCH_SECONDS = 60.0  # total budget: read=30.0 is per-read-op, so a slow
# drip (1 byte per 29s) would otherwise wedge the turn thread indefinitely
_MAX_TEXT_CHARS = 12_000  # guard.py fences tool results at 16k; leave JSON headroom
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _decode_ddg_href(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded>&rut=..."""
    if "uddg=" not in href:
        return href
    encoded = parse_qs(urlparse(href).query).get("uddg", [""])[0]
    return encoded or href


class _DdgResultParser(HTMLParser):
    """Collect {title, url, snippet} dicts from DDG's /html results page."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._target: str | None = None   # "title" | "snippet" while inside one
        self._container: str | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if self._target is not None:
            if tag == self._container:
                self._depth += 1
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            url = _decode_ddg_href(dict(attrs).get("href") or "")
            self.results.append({"title": "", "url": url, "snippet": ""})
            self._target, self._container, self._depth = "title", tag, 1
        elif "result__snippet" in classes and self.results:
            self._target, self._container, self._depth = "snippet", tag, 1

    def handle_endtag(self, tag):
        if self._target is None or tag != self._container:
            return
        self._depth -= 1
        if self._depth == 0:
            self._target = None

    def handle_data(self, data):
        if self._target and self.results:
            self.results[-1][self._target] += data


def _search_web(query: str, max_results: int = 5) -> dict:
    query = str(query or "").strip()
    if not query:
        raise ToolError("query must not be empty")
    try:
        max_results = int(max_results)
    except (TypeError, ValueError) as exc:
        raise ToolError("max_results must be a number") from exc
    max_results = max(1, min(max_results, _MAX_RESULTS))
    try:
        resp = httpx.get(_SEARCH_URL, params={"q": query},
                         headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise ToolError(f"web search failed: {exc}") from exc
    if resp.status_code != 200:
        raise ToolError(f"web search unavailable right now (HTTP {resp.status_code}); "
                        "try fetch_url with a known URL instead")
    parser = _DdgResultParser()
    parser.feed(resp.text)
    parser.close()  # convert_charrefs buffers a trailing run near a bare &
    results = [{"title": r["title"].strip()[:300], "url": r["url"],
                "snippet": " ".join(r["snippet"].split())[:500]}
               for r in parser.results if r["url"].startswith("http")]
    if not results:
        raise ToolError("web search returned no results; the search service may be "
                        "rate limiting, try again later or use fetch_url with a known URL")
    return {"results": results[:max_results]}


class _TextExtractor(HTMLParser):
    """Strip tags to text: skip script/style noise, mark block boundaries."""

    _SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head"})
    _BLOCK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4",
                        "h5", "h6", "section", "article", "table", "ul", "ol"})

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        lines = ("".join(self._chunks)).splitlines()
        collapsed = (" ".join(line.split()) for line in lines)
        return "\n".join(line for line in collapsed if line)


def _fetch_url(url: str) -> dict:
    if not isinstance(url, str):
        raise ToolError("url must be a string")
    try:
        validate_url_safe(url)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    hit_byte_cap = False
    try:
        with httpx.stream("GET", url, headers={"User-Agent": _USER_AGENT},
                          timeout=_TIMEOUT, follow_redirects=False) as resp:
            if resp.status_code in _REDIRECT_STATUSES:
                return {"url": url, "status": resp.status_code,
                        "redirect_to": resp.headers.get("location", ""),
                        "note": "redirect not followed; call fetch_url with "
                                "redirect_to to follow it"}
            if resp.status_code != 200:
                raise ToolError(f"could not fetch {url}: HTTP {resp.status_code}")
            content_type = resp.headers.get("content-type", "").lower()
            deadline = time.monotonic() + _MAX_FETCH_SECONDS
            parts: list[bytes] = []
            received = 0
            # no chunk_size: it would route through httpx's ByteChunker, which
            # buffers sub-chunk_size drips and starves the deadline check below
            for chunk in resp.iter_bytes():
                if time.monotonic() > deadline:
                    raise ToolError(f"could not fetch {url}: exceeded "
                                    f"{int(_MAX_FETCH_SECONDS)}s time budget")
                parts.append(chunk)
                received += len(chunk)
                if received >= _MAX_FETCH_BYTES:
                    hit_byte_cap = True
                    break
            body = b"".join(parts)[:_MAX_FETCH_BYTES]
            encoding = resp.encoding or "utf-8"
    except httpx.HTTPError as exc:
        raise ToolError(f"could not fetch {url}: {exc}") from exc
    is_texty = ("text/" in content_type or "json" in content_type
                or "xml" in content_type or content_type == "")
    if not is_texty:
        raise ToolError(f"unsupported content type {content_type!r}; only HTML, "
                        "text, JSON and XML pages can be fetched")
    try:
        text = body.decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        # hostile/unknown charset (e.g. zlib_codec -> LookupError, idna ->
        # UnicodeError with errors="replace" unsupported): fall back to utf-8
        text = body.decode("utf-8", errors="replace")
    if "html" in content_type:
        extractor = _TextExtractor()
        extractor.feed(text)
        extractor.close()  # flush the trailing buffered text run
        text = extractor.text()
    return {"url": url, "status": 200, "content_type": content_type,
            "text": text[:_MAX_TEXT_CHARS],
            "truncated": hit_byte_cap or len(text) > _MAX_TEXT_CHARS}


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        "search_web",
        "Search the public web (DuckDuckGo). Returns result titles, URLs and snippets.",
        {"type": "object",
         "properties": {
             "query": {"type": "string", "description": "Search query."},
             "max_results": {"type": "integer", "minimum": 1, "maximum": 8,
                             "description": "How many results to return (default 5)."},
         },
         "required": ["query"]},
        _search_web,
    ))
    registry.register(ToolSpec(
        "fetch_url",
        "Fetch one public http(s) page and return its text content. Redirects are "
        "returned in redirect_to, not followed.",
        {"type": "object",
         "properties": {"url": {"type": "string",
                                "description": "Absolute http(s) URL to fetch."}},
         "required": ["url"]},
        _fetch_url,
    ))
