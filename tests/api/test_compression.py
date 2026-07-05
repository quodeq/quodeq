"""gzip after-request hook: compress large JSON, leave everything else alone."""
from __future__ import annotations

import gzip
import json

import pytest
from flask import Flask, Response, jsonify, stream_with_context

from quodeq.api._compression import _MIN_SIZE, configure_compression


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    configure_compression(app)

    @app.get("/big")
    def big() -> Response:
        # Comfortably over the threshold once serialized.
        return jsonify({"items": [{"i": i, "pad": "x" * 64} for i in range(20_000)]})

    @app.get("/small")
    def small() -> Response:
        return jsonify({"ok": True})

    @app.get("/stream")
    def stream() -> Response:
        def gen():
            for i in range(50_000):
                yield f"data: {i}\n\n"
        return Response(stream_with_context(gen()), mimetype="text/event-stream")

    @app.get("/plaintext-big")
    def plaintext_big() -> Response:
        return Response("z" * (_MIN_SIZE + 10), mimetype="text/plain")

    return app


def test_large_json_is_gzipped_and_roundtrips(app: Flask) -> None:
    client = app.test_client()
    resp = client.get("/big", headers={"Accept-Encoding": "gzip"})
    assert resp.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in resp.headers["Vary"]
    # Content-Length must describe the compressed body actually sent.
    assert int(resp.headers["Content-Length"]) == len(resp.get_data())
    decoded = json.loads(gzip.decompress(resp.get_data()))
    assert len(decoded["items"]) == 20_000


def test_no_gzip_without_accept_encoding(app: Flask) -> None:
    resp = app.test_client().get("/big")  # no Accept-Encoding
    assert "Content-Encoding" not in resp.headers
    json.loads(resp.get_data())  # still valid, uncompressed


def test_small_json_is_not_gzipped(app: Flask) -> None:
    resp = app.test_client().get("/small", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in resp.headers


def test_streamed_response_is_never_touched(app: Flask) -> None:
    """SSE streams must stay unbuffered and unencoded — compressing here would
    collect the whole generator into memory and break incremental delivery."""
    resp = app.test_client().get("/stream", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in resp.headers
    assert resp.mimetype == "text/event-stream"


def test_non_json_is_not_gzipped(app: Flask) -> None:
    resp = app.test_client().get("/plaintext-big", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in resp.headers


def test_explicit_gzip_refusal_is_honored(app: Flask) -> None:
    """``gzip;q=0`` is an explicit refusal — the body must go out uncompressed
    even though it clears the size threshold."""
    resp = app.test_client().get("/big", headers={"Accept-Encoding": "gzip;q=0"})
    assert "Content-Encoding" not in resp.headers
    json.loads(resp.get_data())  # valid, uncompressed
