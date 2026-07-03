"""Opt-in web tools for local providers: DuckDuckGo search + guarded URL fetch.

NEVER registered from build_registry(): the MCP server builds its registry
there, and web tools reaching the MCP server would hand the claude CLI web
access with the drawer toggle OFF (its --allowedTools blanket-allows every
tool on the quodeq-assistant server). register_web_tools() is called only
from the orchestrator's API branch, gated on web_enabled + LOCAL_PROVIDERS.
"""
from __future__ import annotations

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
    query = (query or "").strip()
    if not query:
        raise ToolError("query must not be empty")
    max_results = max(1, min(int(max_results), _MAX_RESULTS))
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
    results = [{"title": r["title"].strip(), "url": r["url"],
                "snippet": " ".join(r["snippet"].split())}
               for r in parser.results if r["url"].startswith("http")]
    if not results:
        raise ToolError("web search returned no results; the search service may be "
                        "rate limiting, try again later or use fetch_url with a known URL")
    return {"results": results[:max_results]}
