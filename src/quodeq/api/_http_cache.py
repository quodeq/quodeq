"""Reusable HTTP-cache helpers for UI data-unit endpoints.

etag_for / conditional_json: strong ETag + 304 handling so an unchanged unit
costs a bodyless 304 and no client re-parse. gzip is handled separately and
app-wide by ``_compression.configure_compression`` — not here.
"""
from __future__ import annotations

import hashlib
import json as _json

from flask import Response, request


def etag_for(payload_bytes: bytes) -> str:
    """Strong, quoted ETag from the exact response bytes."""
    digest = hashlib.sha256(payload_bytes).hexdigest()[:32]
    return f'"{digest}"'


def conditional_json(payload: object, *, max_age: int = 0) -> Response:
    """Serialize *payload* to JSON with an ETag; 304 when If-None-Match matches.

    The ETag is computed over compact JSON bytes; the same encoding is used for
    the body so the tag always matches what we send.
    """
    body = _json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    tag = etag_for(body)
    if request.headers.get("If-None-Match") == tag:
        resp = Response(status=304)
        resp.headers["ETag"] = tag
        return resp
    resp = Response(body, mimetype="application/json")
    resp.headers["ETag"] = tag
    if max_age > 0:
        resp.headers["Cache-Control"] = f"private, max-age={max_age}"
    return resp
