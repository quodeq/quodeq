from __future__ import annotations

import json

from flask import Flask

from quodeq.api._http_cache import etag_for, conditional_json


def test_etag_is_stable_and_quoted():
    a = etag_for(b'{"x":1}')
    b = etag_for(b'{"x":1}')
    c = etag_for(b'{"x":2}')
    assert a == b and a != c
    assert a.startswith('"') and a.endswith('"')


def _compact(payload):
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def test_conditional_json_returns_304_on_match():
    app = Flask(__name__)
    with app.test_request_context(headers={"If-None-Match": etag_for(_compact({"k": 1}))}):
        resp = conditional_json({"k": 1})
        assert resp.status_code == 304
        assert resp.get_data() == b""


def test_conditional_json_returns_200_with_etag_on_miss():
    app = Flask(__name__)
    with app.test_request_context(headers={"If-None-Match": '"stale"'}):
        resp = conditional_json({"k": 1})
        assert resp.status_code == 200
        assert resp.headers["ETag"] == etag_for(_compact({"k": 1}))
        assert json.loads(resp.get_data()) == {"k": 1}
