"""Log streaming routes — exposes buffered server logs via REST."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.api._log_buffer import LogBuffer


def register_log_routes(app: Flask, log_buffer: LogBuffer) -> None:
    """Register the /api/logs endpoint."""

    @app.get("/api/logs")
    def get_logs() -> Response:
        since = request.args.get("since", type=int)
        return jsonify(log_buffer.get_lines(since=since))

    @app.get("/logs")
    def logs_page() -> Response:
        html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Quodeq — Server Logs</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117; color: #c9d1d9;
    font-family: ui-monospace, 'SF Mono', Menlo, monospace;
    font-size: 13px; line-height: 1.7;
    padding: 16px;
  }
  h1 {
    font-size: 14px; font-weight: 500;
    color: #8b949e; margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #21262d;
  }
  #logs { white-space: pre-wrap; word-break: break-word; }
  .ts { color: #484f58; }
</style>
</head>
<body>
<h1>Quodeq Server Logs</h1>
<div id="logs"></div>
<script>
let since = -1;
const el = document.getElementById('logs');
async function poll() {
  try {
    const url = '/api/logs' + (since >= 0 ? '?since=' + since : '');
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    if (data.lines.length) {
      const frag = document.createDocumentFragment();
      data.lines.forEach(e => {
        const line = document.createElement('div');
        const ts = e.timestamp ? e.timestamp.slice(11, 19) : '';
        const ets = ts.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        line.innerHTML = '<span class="ts">[' + ets + ']</span> ' +
          e.line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        frag.appendChild(line);
        since = e.index;
      });
      el.appendChild(frag);
      window.scrollTo(0, document.body.scrollHeight);
    }
  } catch {}
}
poll();
setInterval(poll, 2000);
</script>
</body>
</html>"""
        return Response(html, content_type="text/html")
