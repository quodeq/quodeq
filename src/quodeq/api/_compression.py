"""Opt-in gzip for large JSON responses.

The score/dashboard endpoints return multi-megabyte JSON on long-lived
projects. Slimming (dashboard history keys, explorer identity-only violations)
removed the avoidable bulk, but the accumulated scores payload
(``/scores?asOf=``) is still large because its violation/compliance bodies
feed the Overview drill-in and the Violations/Map pages. gzip is the cheap
catch-all for what can't be slimmed without a UI-side lazy-load refactor.

Deliberately narrow to stay safe:

* Only ``application/json`` above ``_MIN_SIZE`` bytes — small responses gain
  nothing and pay compression latency.
* Never streamed or ``direct_passthrough`` responses: SSE log/event streams
  (``text/event-stream`` generators) and ``send_file`` downloads (the project
  ZIP export) must reach the client byte-for-byte, unbuffered.
* Only when the client advertised ``Accept-Encoding: gzip`` and the response
  isn't already encoded.

This runs as an ``after_request`` hook, so it composes with the security-header
hook without ordering constraints (each only mutates the response it's handed).
"""
from __future__ import annotations

import gzip

from flask import Flask, Response, request

# Below this, gzip's CPU + latency outweighs the transfer saving. The score
# endpoints clear it by orders of magnitude; typical CRUD/status JSON won't.
_MIN_SIZE = 500_000
# Level 6 is zlib's default: ~5x on these payloads at a fraction of the cost of
# level 9, which buys little on already-repetitive JSON.
_LEVEL = 6


def configure_compression(app: Flask) -> None:
    """Register the size-gated gzip ``after_request`` hook on *app*."""

    @app.after_request
    def _gzip_large_json(response: Response) -> Response:
        # Streamed (SSE) and passthrough (send_file) responses have no
        # in-memory body to compress and must not be buffered here.
        if response.direct_passthrough or response.is_streamed:
            return response
        if response.mimetype != "application/json":
            return response
        if response.headers.get("Content-Encoding"):
            return response
        # request.accept_encodings honours q-values: `gzip;q=0` is an explicit
        # refusal and an absent header means "don't compress". A plain
        # substring test would wrongly compress for `gzip;q=0`.
        if not request.accept_encodings.quality("gzip"):
            return response
        # Reading .data on a non-streamed response is the already-materialized
        # body; no extra buffering beyond what Flask holds.
        body = response.get_data()
        if len(body) < _MIN_SIZE:
            return response
        compressed = gzip.compress(body, _LEVEL)
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(compressed))
        # Caches must key on Accept-Encoding so a gzip body isn't served to a
        # client that didn't ask for it.
        response.headers.add("Vary", "Accept-Encoding")
        return response
