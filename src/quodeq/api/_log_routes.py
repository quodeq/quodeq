"""Log streaming routes — exposes buffered server logs via REST, plus a
tiny standalone viewer page.

The viewer's CSS/JS are served from their own explicit routes (rather than
inlined into the HTML) so the page's own script-src 'self' CSP directive
(api/security.py) doesn't block it -- an inline <script> tag was silently
dead in real browsers before this split.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._log_buffer import LogBuffer

_LOG_POLL_INTERVAL_MS = 2000
_PAGES_DIR = Path(__file__).resolve().parent / "pages"


def register_log_routes(app: Flask, log_buffer: LogBuffer) -> None:
    """Register the /api/logs endpoint and the /logs viewer page."""
    html = (_PAGES_DIR / "logs.html").read_text(encoding="utf-8")
    css = (_PAGES_DIR / "logs.css").read_text(encoding="utf-8")
    js_template = (_PAGES_DIR / "logs.js").read_text(encoding="utf-8")
    js = js_template.replace("{{POLL_INTERVAL_MS}}", str(_LOG_POLL_INTERVAL_MS))

    @app.get("/api/logs")
    def get_logs() -> Response:
        since = request.args.get("since", type=int)
        return jsonify(log_buffer.get_lines(since=since))

    @app.get("/logs")
    def logs_page() -> Response:
        return Response(html, content_type="text/html")

    @app.get("/logs.css")
    def logs_css() -> Response:
        return Response(css, content_type="text/css")

    @app.get("/logs.js")
    def logs_js() -> Response:
        return Response(js, content_type="application/javascript")
